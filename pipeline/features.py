"""Features for the heatwave warning model (Stage E), shared with Stage F (case study) and the dashboard export.

Task (operational): for every cell-day that is not already in a *confirmed* heatwave (SST above the threshold for at
least 5 days in a row by that day), predict whether the cell will be in a heatwave on any of the next 7 days. Every
feature uses only what is known on the forecast day; the fixed 1991–2020 climatology of the coming calendar days is
known in advance. The hindsight heatwave flag is used only for the label. experiments/leakage_audit.py verifies this
by recomputing every input from data cut off at the forecast day.

Two Spark passes build the features:
  1. per cell (groupBy cell_id): time-series features from the cell's own history  -> lake/cell_features
  2. per day  (groupBy date):    neighbourhood features from the whole grid         -> lake/nb_features
"""
import numpy as np
import pandas as pd
from pyspark.sql import Window
from pyspark.sql import functions as F
from scipy import ndimage

from hot_oceans import grid, hobday, runlog

HORIZON = 7
CELL_FEATURES = ["ratio", "ratio_7", "ratio_30", "ratio_trend_3", "trend_1", "trend_3", "trend_7", "run_len",
                 "days_since_exceed", "exceed_days_30", "ratio_max_7", "gap_to_thr_ahead", "thr_tend_7", "clim_tend_7"]
NB_FEATURES = ["nb_ratio", "nb_ratio_7", "nb_ratio_21", "nb_ratio_max_7", "nb_exceed", "nb_exceed_7", "nb_exceed_21",
               "nb_confirmed"]
FEATURES = CELL_FEATURES + NB_FEATURES + ["nb_exceed_trend_3"]

CELL_SCHEMA = ("cell_id int, date date, year smallint, exceed tinyint, in_mhw tinyint, confirmed tinyint, label double, "
               + ", ".join(f"{c} float" for c in CELL_FEATURES))
NB_SCHEMA = "cell_id int, date date, " + ", ".join(f"{c} float" for c in NB_FEATURES)

_RING = np.ones((3, 3))
_RING[1, 1] = 0          # the 8 surrounding cells, not the cell itself
_PAD = 11                # > half of the largest window (21), so windows at the edge see empty (non-ocean) cells


# ---------------------------------------------------------------- pass 1: per cell
def run_length(flag):
    """Consecutive days with flag set, ending on each day (0 where not set)."""
    i = np.arange(len(flag))
    last_off = np.maximum.accumulate(np.where(flag, -1, i))
    return np.where(flag, i - last_off, 0)


def days_since(flag, cap=365):
    i = np.arange(len(flag))
    last_on = np.maximum.accumulate(np.where(flag, i, -10 ** 9))
    return np.minimum(i - last_on, cap)


def cell_features(pdf: pd.DataFrame) -> pd.DataFrame:
    """One cell's full daily series (contiguous days) -> label, flags and time-series features."""
    pdf = pdf.sort_values("date").reset_index(drop=True)
    dates = pd.DatetimeIndex(pd.to_datetime(pdf["date"]))
    sst, clim, thr = (pdf[c].to_numpy(np.float64) for c in ("sst", "clim", "thresh"))
    anom, ratio = sst - clim, pdf["ratio"].to_numpy(np.float64)
    in_mhw, exceed = pdf["category"].to_numpy() > 0, sst > thr
    n = len(pdf)

    out = pd.DataFrame({"cell_id": pdf["cell_id"].to_numpy(), "date": pdf["date"].to_numpy(),
                        "year": dates.year.astype(np.int16)})
    out["exceed"], out["in_mhw"] = exceed.astype(np.int8), in_mhw.astype(np.int8)
    # Confirmed in real time: above the threshold for 5+ days in a row up to today. (The hindsight flag would also
    # mark the 1-2 day gaps that Hobday joins, but a gap is joined only if the *next* run lasts 5 days.)
    out["confirmed"] = (run_length(exceed) >= 5).astype(np.int8)
    cs = np.concatenate([[0], np.cumsum(in_mhw)])
    label = np.full(n, np.nan)
    label[:n - HORIZON] = (cs[HORIZON + 1:n + 1] - cs[1:n - HORIZON + 1]) > 0   # in a heatwave on t+1 .. t+7

    r, a = pd.Series(ratio), pd.Series(anom)
    out["label"] = label
    out["ratio"] = ratio
    out["ratio_7"], out["ratio_30"] = r.rolling(7).mean(), r.rolling(30).mean()
    out["ratio_trend_3"] = r - r.shift(3)
    for k in (1, 3, 7):
        out[f"trend_{k}"] = a - a.shift(k)
    out["run_len"] = run_length(exceed)
    out["days_since_exceed"] = days_since(exceed)
    out["exceed_days_30"] = pd.Series(exceed.astype(float)).rolling(30).sum()
    out["ratio_max_7"] = r.rolling(7).max()
    # Climatology and threshold of the coming days, from the cell's own (fixed) day-of-year curves.
    doy = hobday.doy366(dates)
    thr_doy, clim_doy = np.full(367, np.nan), np.full(367, np.nan)
    thr_doy[doy], clim_doy[doy] = thr, clim
    ahead = [hobday.doy366(dates + pd.Timedelta(days=k)) for k in range(1, HORIZON + 1)]
    out["gap_to_thr_ahead"] = np.min([thr_doy[d] for d in ahead], axis=0) - sst   # warming needed to cross next week
    out["thr_tend_7"] = thr_doy[ahead[-1]] - thr
    out["clim_tend_7"] = clim_doy[ahead[-1]] - clim
    out[CELL_FEATURES] = out[CELL_FEATURES].astype(np.float32)
    return out


def ensure_cell_features(spark, cfg, force: bool = False):
    root, out = cfg.data("lake", "sst_anom"), cfg.data("lake", "cell_features")
    for b in sorted(p.name.split("=")[1] for p in root.glob("cell_bucket=*")):
        dst = out / f"cell_bucket={b}"
        if (dst / "_SUCCESS").exists() and not force:
            continue
        with runlog.timed(cfg, "E", f"cell_features_bucket_{b}", dst) as rec:
            spark.read.parquet(str(root / f"cell_bucket={b}")) \
                 .select("cell_id", "date", "sst", "clim", "thresh", "ratio", "category") \
                 .groupBy("cell_id").applyInPandas(cell_features, schema=CELL_SCHEMA) \
                 .write.mode("overwrite").parquet(str(dst))
            rec["rows"] = spark.read.parquet(str(dst)).count()


# ---------------------------------------------------------------- pass 2: per day (whole grid)
def _ring_mean(val, mask):
    s, n = ndimage.convolve(val, _RING, mode="constant"), ndimage.convolve(mask, _RING, mode="constant")
    with np.errstate(all="ignore"):
        return np.where(n > 0, s / n, np.nan)


def _box_mean(val, mask, k):
    s = ndimage.uniform_filter(val, size=k, mode="constant")
    n = ndimage.uniform_filter(mask, size=k, mode="constant")
    with np.errstate(all="ignore"):
        return np.where(n > 1e-9, s / n, np.nan)


def neighbours_for_day(pdf: pd.DataFrame) -> pd.DataFrame:
    """One day, all cells: ratio and threshold-exceedance of the surrounding water at three scales."""
    r, c = grid.row_col(pdf["cell_id"].to_numpy())
    rr, cc = r - r.min() + _PAD, c - c.min() + _PAD
    shape = (rr.max() + _PAD + 1, cc.max() + _PAD + 1)

    def g(v, fill=0.0):
        a = np.full(shape, fill)
        a[rr, cc] = v
        return a

    ratio = np.nan_to_num(pdf["ratio"].to_numpy(np.float64), nan=0.0)
    mask, R, E = g(1.0), g(ratio), g(pdf["exceed"].to_numpy(np.float64))
    Cf = g(pdf["confirmed"].to_numpy(np.float64))
    out = pdf[["cell_id", "date"]].copy()
    out["nb_ratio"] = _ring_mean(R, mask)[rr, cc]
    out["nb_ratio_7"] = _box_mean(R, mask, 7)[rr, cc]
    out["nb_ratio_21"] = _box_mean(R, mask, 21)[rr, cc]
    out["nb_ratio_max_7"] = ndimage.maximum_filter(g(ratio, fill=-9.0), size=7, mode="constant", cval=-9.0)[rr, cc]
    out["nb_exceed"] = _ring_mean(E, mask)[rr, cc]
    out["nb_exceed_7"] = _box_mean(E, mask, 7)[rr, cc]
    out["nb_exceed_21"] = _box_mean(E, mask, 21)[rr, cc]
    out["nb_confirmed"] = _ring_mean(Cf, mask)[rr, cc]
    for col in NB_FEATURES:
        out[col] = out[col].astype(np.float32)
    return out


def ensure_neighbours(spark, cfg, force: bool = False):
    out = cfg.data("lake", "nb_features")
    if (out / "_SUCCESS").exists() and not force:
        return
    with runlog.timed(cfg, "E", "nb_features", out) as rec:
        spark.read.parquet(str(cfg.data("lake", "cell_features"))) \
             .select("cell_id", "date", "ratio", "exceed", "confirmed") \
             .groupBy("date").applyInPandas(neighbours_for_day, schema=NB_SCHEMA) \
             .withColumn("cell_bucket", (F.col("cell_id") % cfg["grid"]["n_buckets"]).cast("int")) \
             .write.mode("overwrite").partitionBy("cell_bucket").parquet(str(out))
        rec["rows"] = spark.read.parquet(str(out)).count()


# ---------------------------------------------------------------- model rows
def rows(spark, cfg, cells_df, bucket=None, require_label=True, since=None, cell_id=None):
    """Cell-days eligible for a warning (not in a confirmed heatwave) with all features, label and region tags.
    `since` (a date string) and `cell_id` restrict the rows early, before the window function."""
    def read(name):
        p = cfg.data("lake", name)
        df = spark.read.parquet(str(p / f"cell_bucket={bucket}")) if bucket is not None \
            else spark.read.parquet(str(p)).drop("cell_bucket")
        if since is not None:
            df = df.filter(F.col("date") >= F.date_sub(F.lit(since).cast("date"), 3))
        if cell_id is not None:
            df = df.filter(F.col("cell_id") == cell_id)
        return df
    w = Window.partitionBy("cell_id").orderBy("date")
    df = read("cell_features").join(read("nb_features"), on=["cell_id", "date"]) \
        .withColumn("nb_exceed_trend_3", F.col("nb_exceed_7") - F.lag("nb_exceed_7", 3).over(w)) \
        .join(F.broadcast(cells_df.select("cell_id", "ecoregion", "sector")), on="cell_id") \
        .filter("confirmed = 0")
    if since is not None:
        df = df.filter(F.col("date") >= F.lit(since).cast("date"))
    if require_label:
        df = df.filter(F.col("label").isNotNull())
    return df


def best_model(cfg):
    """(name, warning threshold) of the model chosen on the validation years by Stage E."""
    import json
    m = json.loads(cfg.out("tables", "model_metrics.json").read_text())
    name = m.get("best_model", "random_forest")
    return name, m[name].get("threshold_best_f1_val", 0.5)
