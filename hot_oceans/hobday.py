"""Marine heatwave climatology and detection for one cell (Hobday et al. 2016; categories Hobday et al. 2018).

Pure numpy/pandas so it can be unit-tested without Spark; Stage B calls it per cell inside applyInPandas.
"""
import numpy as np
import pandas as pd


def doy366(dates: pd.DatetimeIndex) -> np.ndarray:
    """Day of year on a 366-day calendar: non-leap days from 1 March shift by one, so 60 is always 29 Feb."""
    doy = dates.dayofyear.to_numpy().copy()
    doy[(~dates.is_leap_year) & (dates.month > 2)] += 1
    return doy


def _smooth_circular(v: np.ndarray, width: int) -> np.ndarray:
    pad = width // 2
    ext = np.concatenate([v[-pad:], v, v[:pad]])
    return np.convolve(ext, np.ones(width) / width, mode="valid")


def climatology(dates, sst, base_start, base_end, half_width=5, smooth_width=31, percentile=90):
    """Return (seasonal mean, threshold), each an array of 366 values indexed by doy366 - 1."""
    dates = pd.DatetimeIndex(dates)
    sst = np.asarray(sst, dtype=float)
    m = (dates >= pd.Timestamp(base_start)) & (dates <= pd.Timestamp(base_end))
    d, x = dates[m], sst[m]
    years = d.year.to_numpy()
    uy = np.unique(years)
    mat = np.full((len(uy), 366), np.nan)
    mat[np.searchsorted(uy, years), doy366(d) - 1] = x
    # Pool every year's values within +/- half_width days of each calendar day.
    pooled = np.concatenate([np.roll(mat, s, axis=1) for s in range(-half_width, half_width + 1)], axis=0)
    with np.errstate(all="ignore"):
        seas = np.nanmean(pooled, axis=0)
        thresh = np.nanpercentile(pooled, percentile, axis=0)
    return _smooth_circular(seas, smooth_width), _smooth_circular(thresh, smooth_width)


def _runs(mask: np.ndarray) -> list[tuple[int, int]]:
    m = np.concatenate([[0], mask.astype(np.int8), [0]])
    d = np.diff(m)
    return list(zip(np.where(d == 1)[0], np.where(d == -1)[0] - 1))


def detect(dates, sst, seas, thresh, min_duration=5, max_gap=2) -> pd.DataFrame:
    """Flag heatwave days. Dates must be consecutive daily values (missing days as NaN)."""
    dates = pd.DatetimeIndex(dates)
    sst = np.asarray(sst, dtype=float)
    i = doy366(dates) - 1
    clim, thr = seas[i], thresh[i]
    exceed = np.nan_to_num(sst, nan=-np.inf) > thr

    merged: list[list[int]] = []
    for s, e in _runs(exceed):
        if e - s + 1 < min_duration:
            continue
        if merged and s - merged[-1][1] - 1 <= max_gap:
            merged[-1][1] = e
        else:
            merged.append([s, e])

    event_no = np.zeros(len(sst), dtype=np.int32)
    for k, (s, e) in enumerate(merged, start=1):
        event_no[s:e + 1] = k

    anomaly = sst - clim
    gap = thr - clim
    with np.errstate(all="ignore"):
        ratio = np.where(gap > 0, anomaly / gap, np.nan)
    # Category = multiple of the threshold-climatology gap: 1 Moderate, 2 Strong, 3 Severe, 4 Extreme.
    cat = np.clip(np.floor(np.nan_to_num(ratio, nan=1.0)), 1, 4)
    category = np.where(event_no > 0, cat, 0).astype(np.int8)
    return pd.DataFrame({
        "clim": clim.astype(np.float32), "thresh": thr.astype(np.float32),
        "anomaly": anomaly.astype(np.float32), "ratio": ratio.astype(np.float32),
        "category": category, "event_no": event_no,
    })
