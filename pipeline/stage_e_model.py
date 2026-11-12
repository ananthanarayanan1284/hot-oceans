"""Stage E — week-ahead marine heatwave warning (Spark MLlib Gradient-Boosted Trees and Random Forest).

Task: for every cell-day not already in a confirmed heatwave, will the cell be in a heatwave on any of the next
7 days? Features use only information available on the day (pipeline/features.py).

Evaluation: fit years (<= fit_end_year) train the models; validation years (to train_end_year) drive GBT early
stopping, the warning thresholds and the choice of the best model; test years (> train_end_year) are used only
for the reported scores. The persistence baseline scores each cell-day by today's intensity ratio. Scores are also
reported on the strict onset subset (water still below the threshold today). Optional spatial cross-validation
holds out groups of ecoregions to test transfer to unseen regions."""
import json

from hot_oceans import cli, runlog  # first: sets Windows env fixes before numpy is used
from hot_oceans.spark import get_spark

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from pyspark.ml import Pipeline  # noqa: E402
from pyspark.ml.classification import GBTClassifier, RandomForestClassifier  # noqa: E402
from pyspark.ml.evaluation import BinaryClassificationEvaluator  # noqa: E402
from pyspark.ml.feature import VectorAssembler  # noqa: E402
from pyspark.ml.functions import vector_to_array  # noqa: E402
from pyspark.sql import functions as F  # noqa: E402

from pipeline import features  # noqa: E402


def best_f1_threshold(pdf: pd.DataFrame, score: str) -> float:
    """Threshold with the best F1 on a uniform (unthinned) sample."""
    y = pdf["label"].to_numpy() == 1
    s = pdf[score].to_numpy()
    best, best_f1 = 0.5, -1.0
    for t in np.unique(np.quantile(s, np.linspace(0.5, 0.995, 200))):
        p = s >= t
        tp, fp, fn = (p & y).sum(), (p & ~y).sum(), (~p & y).sum()
        f1 = 2 * tp / max(2 * tp + fp + fn, 1)
        if f1 > best_f1:
            best, best_f1 = float(t), f1
    return best


def prf(sdf, score: str, thr: float) -> dict:
    hit, pos = F.col(score) >= thr, F.col("label") == 1
    r = sdf.select(F.sum((hit & pos).cast("long")).alias("tp"), F.sum((hit & ~pos).cast("long")).alias("fp"),
                   F.sum((~hit & pos).cast("long")).alias("fn")).first()
    tp, fp, fn = r.tp or 0, r.fp or 0, r.fn or 0
    precision, recall = tp / max(tp + fp, 1), tp / max(tp + fn, 1)
    return {"threshold": thr, "precision": precision, "recall": recall,
            "f1": 2 * precision * recall / max(precision + recall, 1e-9)}


def sample_pdf(sdf, cols, n=400_000, seed=0) -> pd.DataFrame:
    total = sdf.count()
    return sdf.select(*cols).sample(fraction=min(1.0, n / max(total, 1)), seed=seed).toPandas()


def build_training_table(spark, cfg, force):
    """Per bucket: eligible rows, split into fit / val / test, thinned in the fit years (weights undo the thinning)."""
    m = cfg["model"]
    s = m["sample"][cfg.mode]
    out_root = cfg.data("lake", "training_v2")
    cells = spark.read.format("geoparquet").load(str(cfg.data("lake", "cells")))
    for b in sorted(p.name.split("=")[1] for p in cfg.data("lake", "cell_features").glob("cell_bucket=*")):
        out = out_root / f"cell_bucket={b}"
        if (out / "_SUCCESS").exists() and not force:
            continue
        with runlog.timed(cfg, "E", f"training_bucket_{b}", out) as rec:
            df = features.rows(spark, cfg, cells, bucket=b).na.drop(subset=features.FEATURES)
            split = F.when(F.col("year") <= m["fit_end_year"], "fit") \
                     .when(F.col("year") <= m["train_end_year"], "val").otherwise("test")
            pos = F.col("label") == 1
            keep = F.when(split == "fit", F.when(pos, s["fit_positive"]).otherwise(s["fit_negative"])) \
                    .when(split == "val", s["val"]).otherwise(s["test"])
            df = df.withColumn("split", split).withColumn("keep", keep) \
                   .filter(F.rand(seed=int(b)) < F.col("keep")) \
                   .withColumn("weight", 1.0 / F.col("keep"))
            df.select("cell_id", "date", "year", "ecoregion", "sector", "split", "weight", "label", *features.FEATURES) \
              .write.mode("overwrite").parquet(str(out))
            rec["rows"] = spark.read.parquet(str(out)).count()


def gbt(m, with_validation=True):
    g = m["gbt"]
    kw = dict(labelCol="label", weightCol="w", maxIter=g["max_iter"], maxDepth=g["max_depth"], stepSize=g["step_size"],
              subsamplingRate=g["subsampling_rate"], featureSubsetStrategy=g["feature_subset"], seed=42)
    if with_validation:
        kw.update(validationIndicatorCol="is_val", validationTol=g["validation_tol"])
    return GBTClassifier(**kw)


def rf(m):
    return RandomForestClassifier(labelCol="label", weightCol="w", numTrees=m["rf_trees"], maxDepth=m["rf_max_depth"],
                                  featureSubsetStrategy="sqrt", seed=42)


def main():
    cfg, args = cli.parse(__doc__)
    m = cfg["model"]
    spark = get_spark(cfg, "stage-e")

    # 1. Features (two Spark passes) and the training table.
    features.ensure_cell_features(spark, cfg, force=args.force)
    features.ensure_neighbours(spark, cfg, force=args.force)
    build_training_table(spark, cfg, args.force)

    data = spark.read.parquet(str(cfg.data("lake", "training_v2"))) \
                .withColumn("fold", F.abs(F.hash(F.coalesce("ecoregion", "sector"))) % m["n_spatial_folds"]) \
                .withColumn("ratio_score", F.col("ratio").cast("double"))
    # Weights: undo the fit-year thinning, normalised so the fit years and the validation years weigh the same per row.
    fit = data.filter("split = 'fit'")
    mean_w = fit.agg(F.avg("weight")).first()[0]
    data = data.withColumn("w", F.when(F.col("split") == "fit", F.col("weight") / mean_w).otherwise(1.0)) \
               .withColumn("is_val", F.col("split") == "val")
    fit, val, test = (data.filter(F.col("split") == s).cache() for s in ("fit", "val", "test"))
    onset = test.filter("run_len = 0")      # strict onset subset: water still below the threshold today

    pr = BinaryClassificationEvaluator(labelCol="label", metricName="areaUnderPR")
    roc = BinaryClassificationEvaluator(labelCol="label", metricName="areaUnderROC")
    n_test, n_val = test.count(), val.count()
    metrics = {"task": "in a heatwave on any of the next 7 days, for cell-days not in a confirmed heatwave",
               "features": features.FEATURES, "fit_rows": fit.count(), "val_rows": n_val, "test_rows": n_test,
               "test_positive_rate": test.filter("label = 1").count() / max(n_test, 1),
               "onset_test_rows": onset.count(),
               "onset_test_positive_rate": onset.filter("label = 1").count() / max(onset.count(), 1),
               "note": "PR-AUC of a random guess equals the positive rate"}

    # 2. Persistence baseline: today's intensity ratio.
    base_pr = BinaryClassificationEvaluator(labelCol="label", rawPredictionCol="ratio_score", metricName="areaUnderPR")
    thr = best_f1_threshold(sample_pdf(val, ["label", "ratio_score"]), "ratio_score")
    metrics["persistence_baseline"] = {"pr_auc_val": base_pr.evaluate(val), "pr_auc_test": base_pr.evaluate(test),
                                       "pr_auc_onset_test": base_pr.evaluate(onset), **prf(test, "ratio_score", thr)}
    print("[E] persistence", metrics["persistence_baseline"])

    # 3. Models. GBT trains on fit + validation rows and stops early on the validation rows; RF trains on fit rows.
    assembler = VectorAssembler(inputCols=features.FEATURES, outputCol="features")
    fitted = {}
    for name, est, train_df in (("gbt", gbt(m), fit.unionByName(val)), ("random_forest", rf(m), fit)):
        with runlog.timed(cfg, "E", f"train_{name}") as rec:
            pipe = Pipeline(stages=[assembler, est]).fit(train_df)
            score = lambda df: pipe.transform(df).withColumn("p", vector_to_array("probability")[1])  # noqa: E731
            pv, pt, po = score(val), score(test), score(onset)
            thr = best_f1_threshold(sample_pdf(pv, ["label", "p"]), "p")
            metrics[name] = {"pr_auc_val": pr.evaluate(pv), "pr_auc_test": pr.evaluate(pt), "roc_auc_test": roc.evaluate(pt),
                             "pr_auc_onset_test": pr.evaluate(po), "threshold_best_f1_val": thr,
                             "test_at_threshold": prf(pt, "p", thr)}
            if name == "gbt":
                metrics[name]["trees_used"] = pipe.stages[-1].getNumTrees
            rec["rows"] = train_df.count()
            pipe.write().overwrite().save(str(cfg.out("models", name)))
            fitted[name] = pipe
            imp = pipe.stages[-1].featureImportances.toArray()
            pd.DataFrame({"feature": features.FEATURES, "importance": imp}).sort_values("importance", ascending=False) \
              .to_csv(cfg.out("tables", f"feature_importance_{name}.csv"), index=False)
            print(f"[E] {name}", metrics[name])

    best = max(("gbt", "random_forest"), key=lambda k: metrics[k]["pr_auc_val"])   # chosen on validation years only
    metrics["best_model"] = best
    pd.read_csv(cfg.out("tables", f"feature_importance_{best}.csv")).to_csv(cfg.out("tables", "feature_importance.csv"), index=False)

    # 4. Optional spatial cross-validation of the best model type: hold out groups of regions in the fit years and
    #    score the held-out regions in the validation years.
    if m["spatial_cv"][cfg.mode]:
        cv = []
        for k in range(m["n_spatial_folds"]):
            held_val = val.filter(F.col("fold") == k)
            if held_val.filter("label = 1").count() == 0:
                continue
            est = gbt(m, with_validation=False).setMaxIter(metrics["gbt"].get("trees_used", m["gbt"]["max_iter"])) \
                if best == "gbt" else rf(m)
            p = Pipeline(stages=[assembler, est]).fit(fit.filter(F.col("fold") != k))
            cv.append(pr.evaluate(p.transform(held_val).withColumn("p", vector_to_array("probability")[1])))
        metrics[best]["pr_auc_spatial_cv_folds"] = cv
        metrics[best]["pr_auc_spatial_cv_mean"] = float(np.mean(cv)) if cv else None

    cfg.out("tables").mkdir(parents=True, exist_ok=True)
    cfg.out("tables", "model_metrics.json").write_text(json.dumps(metrics, indent=2, default=float))
    print(json.dumps(metrics, indent=2, default=float))
    spark.stop()


if __name__ == "__main__":
    main()
