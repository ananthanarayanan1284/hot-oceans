"""Stage E (trust checks) — how far can the warning model be trusted? Run after stage_e_model.

  1. Consistency: PR-AUC of the model and of the persistence rule in every test year and every region.
  2. Confidence: block bootstrap over (year x region) blocks -> 95% intervals for both PR-AUCs and their difference.
  3. Calibration: predicted risk vs observed frequency on the test years, before and after isotonic calibration
     fitted on the validation years (Brier score, expected calibration error).
  4. Lead time on every onset: for all heatwave onsets in the test years in a regular subset of cells, how many days
     before the onset the model (and the rule) first warned.
  5. Negative control: a model trained on random labels must score no better than the positive rate.
The leakage audit (features recomputed from data cut off at the forecast day) is experiments/leakage_audit.py and
the unit test tests/test_hobday.py::test_features_do_not_change_when_the_future_is_removed.

Writes outputs/<mode>/tables/trust_checks.json and trust_*.csv."""
import json

from hot_oceans import cli, runlog  # first: sets Windows env fixes before numpy is used
from hot_oceans.spark import get_spark

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from pyspark.ml import Pipeline, PipelineModel  # noqa: E402
from pyspark.ml.classification import RandomForestClassifier  # noqa: E402
from pyspark.ml.evaluation import BinaryClassificationEvaluator  # noqa: E402
from pyspark.ml.feature import VectorAssembler  # noqa: E402
from pyspark.ml.functions import vector_to_array  # noqa: E402
from pyspark.sql import functions as F  # noqa: E402
from sklearn.isotonic import IsotonicRegression  # noqa: E402
from sklearn.metrics import average_precision_score  # noqa: E402

from pipeline import features  # noqa: E402


def binned_ap_parts(score, label, block, edges):
    """Per-block histograms of positives and negatives over score bins (for a fast block bootstrap of AP)."""
    k = np.clip(np.searchsorted(edges, score, side="right") - 1, 0, len(edges) - 2)
    blocks, b = np.unique(block, return_inverse=True)
    pos = np.zeros((len(blocks), len(edges) - 1))
    neg = np.zeros_like(pos)
    np.add.at(pos, (b[label == 1], k[label == 1]), 1)
    np.add.at(neg, (b[label == 0], k[label == 0]), 1)
    return pos, neg


def ap_from_hist(pos, neg):
    """Average precision from score-bin counts (thresholds at bin edges, highest bin first)."""
    p, n = pos[::-1], neg[::-1]
    tp, fp = np.cumsum(p), np.cumsum(n)
    prec = tp / np.maximum(tp + fp, 1)
    return float(np.sum(prec * p) / max(p.sum(), 1))


def calibration_table(p, y, bins=10):
    q = np.unique(np.quantile(p, np.linspace(0, 1, bins + 1)))
    k = np.clip(np.searchsorted(q, p, side="right") - 1, 0, len(q) - 2)
    t = pd.DataFrame({"bin": k, "p": p, "y": y}).groupby("bin").agg(predicted=("p", "mean"), observed=("y", "mean"),
                                                                    rows=("y", "size"))
    ece = float(np.sum(t.rows * (t.predicted - t.observed).abs()) / t.rows.sum())
    return t.reset_index(drop=True), ece


def lead_times(df, score, thr, horizon):
    """Days of warning before each onset (first day of a heatwave): earliest day in [onset-h, onset-1] with
    score >= thr. Returns one row per onset (lead NaN = no advance warning)."""
    out = []
    for cid, g in df.groupby("cell_id"):
        g = g.sort_values("date")
        d = pd.to_datetime(g.date).to_numpy()
        hot = g.in_mhw.to_numpy() == 1
        warn = (g[score].to_numpy() >= thr) & ~np.isnan(g[score].to_numpy())
        starts = np.where(hot & ~np.concatenate([[True], hot[:-1]]))[0]
        for s in starts:
            if not g.in_test.iloc[s]:
                continue
            lo = max(0, s - horizon)
            w = np.where(warn[lo:s])[0]
            out.append({"cell_id": cid, "onset": d[s], "lead_days": float(s - (lo + w[0])) if len(w) else np.nan})
    return pd.DataFrame(out)


def summarise_leads(lt):
    n = len(lt)
    led = lt.lead_days.dropna()
    return {"onsets": n, "warned_share": len(led) / max(n, 1),
            "warned_3d_or_more_share": float((led >= 3).sum() / max(n, 1)),
            "warned_5d_or_more_share": float((led >= 5).sum() / max(n, 1)),
            "median_lead_days_when_warned": float(led.median()) if len(led) else None}


def main():
    cfg, args = cli.parse(__doc__)
    m = cfg["model"]
    spark = get_spark(cfg, "stage-e-trust")
    metrics = json.loads(cfg.out("tables", "model_metrics.json").read_text())
    best, thr = features.best_model(cfg)
    rule_thr = metrics["persistence_baseline"]["threshold"]
    model = PipelineModel.load(str(cfg.out("models", best)))
    data = spark.read.parquet(str(cfg.data("lake", "training_v2"))) \
                .withColumn("region", F.coalesce("ecoregion", "sector"))
    score = lambda df: model.transform(df).withColumn("p", vector_to_array("probability")[1])  # noqa: E731
    cols = ["label", "p", "ratio", "year", "region", "run_len"]
    # Full basin: ~32M test rows exceed the driver's 1 GB result limit, so a fixed 20% random sample (~6M rows) is used.
    test_frac = 1.0 if cfg.mode == "dev" else 0.2
    test_df = data.filter("split = 'test'")
    if test_frac < 1.0:
        test_df = test_df.sample(fraction=test_frac, seed=42)
    test = score(test_df).select(*cols).toPandas()
    val = score(data.filter("split = 'val'")).select("label", "p").toPandas()
    y, p, r = test.label.to_numpy().astype(int), test.p.to_numpy(), test.ratio.to_numpy()
    res = {"model": best, "threshold": thr, "rule_threshold": rule_thr, "test_rows": len(test), "test_sample_fraction": test_frac,
           "test_positive_rate": float(y.mean())}

    # 1. consistency by year and by region
    def ap_by(key, min_pos=50):
        rows = []
        for k, g in test.groupby(key):
            if g.label.sum() < min_pos:
                continue
            rows.append({key: k, "rows": len(g), "positive_rate": g.label.mean(),
                         "model_pr_auc": average_precision_score(g.label, g.p),
                         "rule_pr_auc": average_precision_score(g.label, g.ratio)})
        t = pd.DataFrame(rows)
        t["model_better"] = t.model_pr_auc > t.rule_pr_auc
        t.to_csv(cfg.out("tables", f"trust_by_{key}.csv"), index=False)
        return t
    by_year, by_region = ap_by("year"), ap_by("region")
    res["years_model_better"] = f"{int(by_year.model_better.sum())} of {len(by_year)}"
    res["regions_model_better"] = f"{int(by_region.model_better.sum())} of {len(by_region)}"
    print(by_year.round(3).to_string(index=False))

    # 2. block bootstrap of PR-AUC (blocks = year x region; whole blocks are resampled to respect autocorrelation)
    with runlog.timed(cfg, "E", "trust_bootstrap") as rec:
        block = test.year.astype(str) + "|" + test.region.astype(str)
        rng = np.random.default_rng(0)
        out = {}
        for name, s in (("model", p), ("rule", r)):
            edges = np.unique(np.quantile(s, np.linspace(0, 1, 2001)))
            out[name] = binned_ap_parts(s, y, block.to_numpy(), edges)
        nb = out["model"][0].shape[0]
        reps = {"model": [], "rule": []}
        for _ in range(1000):
            c = np.bincount(rng.integers(0, nb, nb), minlength=nb)[:, None]
            for name in reps:
                pos, neg = out[name]
                reps[name].append(ap_from_hist((pos * c).sum(0), (neg * c).sum(0)))
        diff = np.array(reps["model"]) - np.array(reps["rule"])
        ci = lambda v: [float(np.percentile(v, 2.5)), float(np.percentile(v, 97.5))]  # noqa: E731
        res["bootstrap"] = {"blocks": int(nb), "replicates": 1000,
                            "model_pr_auc": average_precision_score(y, p), "model_ci95": ci(reps["model"]),
                            "rule_pr_auc": average_precision_score(y, r), "rule_ci95": ci(reps["rule"]),
                            "difference_ci95": ci(diff), "share_of_replicates_model_better": float((diff > 0).mean())}
        rec["rows"] = len(test)
    print("bootstrap", res["bootstrap"])

    # 3. calibration (isotonic fitted on the validation years only)
    iso = IsotonicRegression(out_of_bounds="clip").fit(val.p.to_numpy(), val.label.to_numpy())
    pc = iso.predict(p)
    raw_t, raw_ece = calibration_table(p, y)
    cal_t, cal_ece = calibration_table(pc, y)
    raw_t.assign(version="raw").to_csv(cfg.out("tables", "trust_calibration.csv"), index=False)
    cal_t.assign(version="calibrated").to_csv(cfg.out("tables", "trust_calibration.csv"), mode="a", header=False, index=False)
    res["calibration"] = {"brier_raw": float(np.mean((p - y) ** 2)), "brier_calibrated": float(np.mean((pc - y) ** 2)),
                          "ece_raw": raw_ece, "ece_calibrated": cal_ece,
                          "isotonic_x": iso.X_thresholds_.tolist(), "isotonic_y": iso.y_thresholds_.tolist()}
    print("calibration", {k: round(v, 4) for k, v in res["calibration"].items() if not isinstance(v, list)})

    # 4. lead time on every onset in the test years, for a regular subset of cells (every k-th cell)
    with runlog.timed(cfg, "E", "trust_lead_times") as rec:
        k = 5 if cfg.mode == "dev" else 50
        test_start = f"{m['train_end_year'] + 1}-01-01"
        cells = spark.read.format("geoparquet").load(str(cfg.data("lake", "cells")))
        rows = features.rows(spark, cfg, cells, require_label=False, since=test_start) \
                       .filter(F.col("cell_id") % k == 0).na.drop(subset=features.FEATURES)
        scored = score(rows).select("cell_id", "date", "p", F.col("ratio").alias("rule"))
        flags = spark.read.parquet(str(cfg.data("lake", "cell_features"))) \
                     .filter((F.col("cell_id") % k == 0) & (F.col("date") >= F.date_sub(F.lit(test_start).cast("date"), 10))) \
                     .select("cell_id", "date", "in_mhw")
        lt_df = flags.join(scored, on=["cell_id", "date"], how="left") \
                     .withColumn("in_test", F.col("date") >= F.lit(test_start).cast("date")).toPandas()
        lm = lead_times(lt_df, "p", thr, m["horizon_days"])
        lr = lead_times(lt_df, "rule", rule_thr, m["horizon_days"])
        lm.merge(lr, on=["cell_id", "onset"], suffixes=("_model", "_rule")) \
          .to_csv(cfg.out("tables", "trust_lead_times.csv"), index=False)
        res["lead_times"] = {"cells": int(lt_df.cell_id.nunique()), "model": summarise_leads(lm), "rule": summarise_leads(lr)}
        rec["rows"] = len(lm)
    print("lead times", res["lead_times"])

    # 5. negative control: random labels must give no skill
    with runlog.timed(cfg, "E", "trust_negative_control") as rec:
        fit = data.filter("split = 'fit'")
        share = fit.filter("label = 1").count() / max(fit.count(), 1)
        fake = fit.withColumn("label", (F.rand(seed=123) < share).cast("double"))
        ctrl = Pipeline(stages=[VectorAssembler(inputCols=features.FEATURES, outputCol="features"),
                                RandomForestClassifier(labelCol="label", numTrees=30, maxDepth=10, seed=7)]).fit(fake)
        pr = BinaryClassificationEvaluator(labelCol="label", metricName="areaUnderPR")
        res["negative_control"] = {"pr_auc_test_random_labels": pr.evaluate(ctrl.transform(test_df)),
                                   "test_positive_rate": float(y.mean())}
        rec["rows"] = fake.count()
    print("negative control", res["negative_control"])

    cfg.out("tables", "trust_checks.json").write_text(json.dumps(res, indent=2, default=float))
    spark.stop()


if __name__ == "__main__":
    main()
