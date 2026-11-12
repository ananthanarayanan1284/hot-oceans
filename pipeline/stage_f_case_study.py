"""Stage F — Lakshadweep 2023–24 out-of-sample case study: when did the model warn versus when the heatwave began?"""
import json

from hot_oceans import cli, grid, runlog  # first: sets Windows env fixes before numpy is used
from hot_oceans.spark import get_spark

import matplotlib  # noqa: E402
import pandas as pd  # noqa: E402
from pyspark.ml import PipelineModel  # noqa: E402
from pyspark.ml.functions import vector_to_array  # noqa: E402
from pyspark.sql import functions as F  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from pipeline import features  # noqa: E402

CAT_COLORS = {1: "#E38A1E", 2: "#CF531C", 3: "#A3231B", 4: "#5E1214"}


def main():
    cfg, args = cli.parse(__doc__, lambda ap: ap.add_argument("--threshold", type=float, default=None))
    cs = cfg["case_study"]
    model_name, thr = features.best_model(cfg)   # model and threshold chosen by Stage E on the validation years
    if args.threshold is None:
        args.threshold = thr
    print(f"[F] model = {model_name}, warning threshold = {args.threshold:.3f}")
    spark = get_spark(cfg, "stage-f")
    cid = int(grid.cell_id(cs["lat"], cs["lon"]))
    with runlog.timed(cfg, "F", "case_study") as rec:
        anom = spark.read.parquet(str(cfg.data("lake", "sst_anom"))).filter(F.col("cell_id") == cid)
        if anom.limit(1).count() == 0:
            raise SystemExit(f"cell {cid} not in the lake (land-masked?); move the case-study point offshore")
        cells = spark.read.format("geoparquet").load(str(cfg.data("lake", "cells")))
        feats = features.rows(spark, cfg, cells, bucket=cid % cfg["grid"]["n_buckets"], require_label=False,
                              cell_id=cid).na.drop(subset=features.FEATURES)
        model = PipelineModel.load(str(cfg.out("models", model_name)))
        scored = model.transform(feats).withColumn("p_onset", vector_to_array("probability")[1]) \
                      .select("date", "p_onset")
        series = anom.join(scored, on="date", how="left") \
                     .filter((F.col("date") >= cs["start"]) & (F.col("date") <= cs["end"])) \
                     .select("date", "sst", "clim", "thresh", "category", "p_onset").orderBy("date").toPandas()
        rec["rows"] = len(series)
    series.to_parquet(cfg.out("dashboard", "case_study.parquet"))

    onset = series.loc[series.category > 0, "date"].min()
    warn = series.loc[(series.p_onset >= args.threshold) & (series.date <= onset), "date"].min() if pd.notna(onset) else None
    summary = {"cell_id": cid, "first_heatwave_day": str(onset), "first_warning_day": str(warn),
               "lead_days": (pd.Timestamp(onset) - pd.Timestamp(warn)).days if warn is not None and pd.notna(warn) else None,
               "threshold": args.threshold, "model": model_name}
    cfg.out("tables", "case_study_summary.json").write_text(json.dumps(summary, indent=2))
    print(summary)
    plot(series, cfg, cs["name"])
    spark.stop()


def plot(s: pd.DataFrame, cfg, name: str):
    fig, (ax, ax2) = plt.subplots(2, 1, figsize=(11, 6), sharex=True, gridspec_kw={"height_ratios": [3, 1]})
    d = pd.to_datetime(s.date)
    for c, col in CAT_COLORS.items():
        m = s.category == c
        ax.fill_between(d, s.thresh, s.sst, where=m & (s.sst > s.thresh), color=col, step="mid", label=f"Cat {c}")
    ax.plot(d, s.sst, color="#18262D", lw=1.5, label="SST")
    ax.plot(d, s.thresh, color="#2A78D6", lw=1, label="90th pct threshold")
    ax.plot(d, s.clim, color="#62727B", lw=1, label="Climatology")
    ax.set_ylabel("°C"); ax.legend(ncol=4, fontsize=8, frameon=False); ax.set_title(f"{name}: SST and heatwave categories")
    ax2.plot(d, s.p_onset, color="#0A4F6B"); ax2.set_ylabel("Risk (next 7 d)"); ax2.set_ylim(0, 1)
    fig.tight_layout()
    cfg.out("figures").mkdir(parents=True, exist_ok=True)
    fig.savefig(cfg.out("figures", "case_study.png"), dpi=200)


if __name__ == "__main__":
    main()
