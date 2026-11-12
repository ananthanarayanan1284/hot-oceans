"""Write the small files the dashboard reads (well under 1 GB). Run on the DGX, then rsync outputs/<mode>/ to the PC."""
import datetime
import shutil

from pyspark.ml import PipelineModel
from pyspark.ml.functions import vector_to_array
from pyspark.sql import functions as F

from pipeline import features
from hot_oceans import cli, runlog
from hot_oceans.spark import get_spark


def main():
    cfg, args = cli.parse(__doc__)
    spark = get_spark(cfg, "export")
    out = cfg.out("dashboard")
    out.mkdir(parents=True, exist_ok=True)
    anom = spark.read.parquet(str(cfg.data("lake", "sst_anom")))
    cells = spark.read.format("geoparquet").load(str(cfg.data("lake", "cells")))
    d0, d1 = cfg["dashboard"]["start"], cfg["dashboard"]["end"]

    with runlog.timed(cfg, "G", "export_daily_cat", out / "daily_cat.parquet") as rec:
        daily = anom.filter((F.col("date") >= d0) & (F.col("date") <= d1) & (F.col("category") > 0)) \
                    .select("cell_id", "date", "category", "anomaly").toPandas()
        daily.to_parquet(out / "daily_cat.parquet")
        rec["rows"] = len(daily)

    cells.select("cell_id", "lat", "lon", "sector", "ecoregion", "area_km2").toPandas() \
         .to_parquet(out / "cells.parquet")

    with runlog.timed(cfg, "G", "export_yearly") as rec:
        yearly = anom.groupBy("cell_id", "year").agg(F.sum((F.col("category") > 0).cast("int")).alias("mhw_days")) \
                     .groupBy("year").agg(F.avg("mhw_days").alias("mean_mhw_days")).orderBy("year").toPandas()
        yearly.to_parquet(out / "mhw_days_per_year.parquet")
        rec["rows"] = len(yearly)

    with runlog.timed(cfg, "G", "export_risk") as rec:
        last = anom.agg(F.max("date")).first()[0]
        since = str(last - datetime.timedelta(days=30))
        feats = features.rows(spark, cfg, cells, require_label=False, since=since).na.drop(subset=features.FEATURES)
        model_name, _ = features.best_model(cfg)
        model = PipelineModel.load(str(cfg.out("models", model_name)))
        risk = model.transform(feats).withColumn("p_onset", vector_to_array("probability")[1]) \
                    .select("cell_id", "date", "p_onset").toPandas()
        risk.to_parquet(out / "risk.parquet")
        rec["rows"] = len(risk)

    for name in ("regime_profiles.csv", "regime_by_iod_phase.csv", "rules.csv", "feature_importance.csv",
                 "model_metrics.json", "case_study_summary.json", "run_log.csv", "trust_checks.json",
                 "trust_by_year.csv", "trust_by_region.csv"):
        src = cfg.out("tables", name)
        if src.exists():
            shutil.copy(src, out / name)
    spark.stop()


if __name__ == "__main__":
    main()
