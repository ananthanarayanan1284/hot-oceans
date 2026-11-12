"""Stage D — K-Means heatwave regimes (k chosen by silhouette), regime share by IOD/ENSO phase,
and FP-Growth association rules on event attributes."""
import numpy as np
import pandas as pd
from pyspark.ml import Pipeline
from pyspark.ml.clustering import KMeans
from pyspark.ml.evaluation import ClusteringEvaluator
from pyspark.ml.feature import StandardScaler, VectorAssembler
from pyspark.ml.fpm import FPGrowth

from hot_oceans import cli, climate, db, runlog
from hot_oceans.spark import get_spark

FEATURES = ["log_duration", "log_area", "max_intensity", "mean_intensity", "log_cum", "clat", "clon",
            "month_sin", "month_cos"]


def main():
    cfg, args = cli.parse(__doc__)
    spark = get_spark(cfg, "stage-d")
    ev = pd.read_parquet(cfg.data("lake", "events.parquet"))
    clim = climate.climate_monthly(cfg.aux("dmi.txt"), cfg.aux("oni.txt"),
                                   cfg["phases"]["iod_threshold"], cfg["phases"]["enso_threshold"])
    start = pd.to_datetime(ev.start)
    ev = ev.assign(year=start.dt.year, month=start.dt.month) \
           .merge(clim, on=["year", "month"], how="left")
    ev["log_duration"] = np.log(ev.duration_days)
    ev["log_area"] = np.log(ev.peak_area_km2)
    ev["log_cum"] = np.log1p(ev.cum_intensity.clip(lower=0))
    ev["month_sin"], ev["month_cos"] = np.sin(2 * np.pi * ev.month / 12), np.cos(2 * np.pi * ev.month / 12)
    sdf = spark.createDataFrame(ev[["event_id"] + FEATURES])

    # Regimes: K-Means for k = 3..8, keep the best silhouette.
    with runlog.timed(cfg, "D", "kmeans") as rec:
        prep = Pipeline(stages=[VectorAssembler(inputCols=FEATURES, outputCol="raw"),
                                StandardScaler(inputCol="raw", outputCol="features")]).fit(sdf)
        X = prep.transform(sdf).cache()
        scores = []
        for k in range(3, 9):
            model = KMeans(k=k, seed=42, featuresCol="features").fit(X)
            sil = ClusteringEvaluator(featuresCol="features").evaluate(model.transform(X))
            scores.append((k, sil, model.summary.trainingCost, model))
        best_k, best_sil, _, best = max(scores, key=lambda s: s[1])
        rec["rows"], rec["note"] = len(ev), f"best k={best_k} silhouette={best_sil:.3f}"
    pd.DataFrame([(k, s, c) for k, s, c, _ in scores], columns=["k", "silhouette", "inertia"]) \
        .to_csv(cfg.out("tables", "kmeans_selection.csv"), index=False)
    regimes = best.transform(X).select("event_id", "prediction").toPandas().rename(columns={"prediction": "regime"})
    ev = ev.merge(regimes, on="event_id")
    profile = ev.groupby("regime")[["duration_days", "peak_area_km2", "max_intensity", "clat", "clon"]].mean()
    profile.to_csv(cfg.out("tables", "regime_profiles.csv"))
    for col in ("iod_phase", "enso_phase"):
        pd.crosstab(ev[col], ev.regime, normalize="index").round(3).to_csv(cfg.out("tables", f"regime_by_{col}.csv"))
    ev[["event_id", "regime"]].to_parquet(cfg.data("lake", "event_regimes.parquet"))
    db.write_df(cfg, ev[["event_id", "regime", "iod_phase", "enso_phase"]], "event_regimes")

    # Association rules.
    with runlog.timed(cfg, "D", "fpgrowth") as rec:
        items = ev.apply(lambda r: sorted({
            f"sector={climate.sector(r.clat, r.clon)}", f"season={climate.season(r.month)}",
            f"iod={r.iod_phase}", f"enso={r.enso_phase}",
            "cat=Severe+" if r.max_category >= 3 else ("cat=Strong" if r.max_category == 2 else "cat=Moderate"),
            "long>=30d" if r.duration_days >= 30 else "short<30d",
        }), axis=1)
        tx = spark.createDataFrame(pd.DataFrame({"items": items}))
        fp = FPGrowth(itemsCol="items", minSupport=0.05, minConfidence=0.5).fit(tx)
        rules = fp.associationRules.toPandas()
        rules = rules[rules.consequent.map(lambda c: any(i.startswith(("cat=", "long")) for i in c))]
        rules = rules.sort_values("lift", ascending=False)
        rec["rows"] = len(rules)
    rules.assign(antecedent=rules.antecedent.map(" & ".join), consequent=rules.consequent.map(" & ".join)) \
        .to_csv(cfg.out("tables", "rules.csv"), index=False)
    spark.stop()


if __name__ == "__main__":
    main()
