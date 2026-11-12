"""Stage B — per-cell climatology, 90th-percentile threshold and Hobday heatwave detection.

Runs one cell bucket at a time (resumable). Each cell's ~16k daily values are processed in numpy
inside groupBy(cell_id).applyInPandas, which avoids exploding the 11-day window in Spark SQL.

Output lake/sst_anom/cell_bucket=N/: cell_id, date, year, sst, clim, thresh, anomaly, ratio, category, event_no
"""
import numpy as np
import pandas as pd

from hot_oceans import cli, hobday, runlog
from hot_oceans.spark import get_spark

SCHEMA = ("cell_id int, date date, year smallint, sst float, clim float, thresh float, "
          "anomaly float, ratio float, category tinyint, event_no int")


def make_cell_fn(cfg):
    hb, base = cfg["hobday"], cfg["baseline"]

    def per_cell(pdf: pd.DataFrame) -> pd.DataFrame:
        pdf = pdf.sort_values("date")
        idx = pd.DatetimeIndex(pd.to_datetime(pdf["date"]))
        full = pd.date_range(idx.min(), idx.max(), freq="D")       # detection needs consecutive days
        sst = pd.Series(pdf["sst"].to_numpy(dtype=float), index=idx).reindex(full)
        seas, thresh = hobday.climatology(full, sst.to_numpy(), base["start"], base["end"],
                                          hb["window_half_width"], hb["smooth_width"], hb["percentile"])
        res = hobday.detect(full, sst.to_numpy(), seas, thresh, hb["min_duration"], hb["max_gap"])
        res.insert(0, "sst", sst.to_numpy(dtype=np.float32))
        res.insert(0, "year", full.year.astype(np.int16))
        res.insert(0, "date", full.date)
        res.insert(0, "cell_id", np.int32(pdf["cell_id"].iloc[0]))
        return res[~np.isnan(res["sst"])]

    return per_cell


def main():
    cfg, args = cli.parse(__doc__, lambda ap: ap.add_argument("--buckets", type=int, nargs="*"))
    spark = get_spark(cfg, "stage-b")
    src, dst = cfg.data("lake", "sst_by_cell"), cfg.data("lake", "sst_anom")
    per_cell = make_cell_fn(cfg)
    buckets = args.buckets if args.buckets else range(cfg["grid"]["n_buckets"])

    for b in buckets:
        out = dst / f"cell_bucket={b}"
        if (out / "_SUCCESS").exists() and not args.force:
            continue
        with runlog.timed(cfg, "B", f"detect_bucket_{b}", out) as rec:
            df = spark.read.parquet(str(src / f"cell_bucket={b}"))
            res = df.groupBy("cell_id").applyInPandas(per_cell, schema=SCHEMA)
            res.write.mode("overwrite").parquet(str(out))
            rec["rows"] = spark.read.parquet(str(out)).count()

    with runlog.timed(cfg, "B", "summary") as rec:
        anom = spark.read.parquet(str(dst))
        rec["rows"] = anom.count()
        hot = anom.filter("category > 0").count()
        rec["note"] = f"heatwave cell-days={hot} ({hot / max(rec['rows'], 1):.1%})"
        # Climatology table: any leap year carries all 366 calendar days.
        anom.filter("year = 2000").selectExpr("cell_id", "dayofyear(date) AS doy", "clim", "thresh") \
            .write.mode("overwrite").parquet(str(cfg.data("lake", "climatology")))
    spark.stop()


if __name__ == "__main__":
    main()
