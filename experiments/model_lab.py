"""Fast model lab on the sample box (PC): features as numpy grids [day, row, col] + sklearn HistGradientBoosting.
Used to choose features and the task definition before porting them to the Spark pipeline (Stage E).

    python experiments/model_lab.py            -> experiments/results/lab_results.csv

Split: fit 1982–2014, validation 2015–2018 (model choice), test 2019–2025 (reported, never used for choices).
Scores are average precision (AP, the step-wise PR-AUC); a random guess scores the positive rate."""
import gc
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import hot_oceans  # noqa: F401,E402  (Windows MKL fix before numpy)
from hot_oceans import climate, config  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import pyarrow as pa  # noqa: E402
import pyarrow.dataset as ds  # noqa: E402
from scipy import ndimage  # noqa: E402
from sklearn.ensemble import HistGradientBoostingClassifier  # noqa: E402
from sklearn.metrics import average_precision_score, precision_recall_curve  # noqa: E402

cfg = config.load("pc", "dev")
BOX = cfg.box
R0, C0 = int(round((BOX["lat_min"] + 90) / 0.25)), int(round(BOX["lon_min"] / 0.25))
NR, NC = int(round((BOX["lat_max"] - BOX["lat_min"]) / 0.25)), int(round((BOX["lon_max"] - BOX["lon_min"]) / 0.25))
D0 = np.datetime64("1982-01-01")
DATES = np.arange(D0, np.datetime64("2026-01-01"))
T = len(DATES)
HORIZON = 7
OUT = ROOT / "experiments" / "results"
OUT.mkdir(parents=True, exist_ok=True)
rng = np.random.default_rng(42)


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


# ------------------------------------------------------------------ load the lake into grids
def load():
    sst, clim, thr = (np.full((T, NR, NC), np.nan, np.float32) for _ in range(3))
    cat = np.zeros((T, NR, NC), np.int8)
    epoch0 = int((D0 - np.datetime64("1970-01-01")).astype(int))
    dset = ds.dataset(str(cfg.data("lake", "sst_anom")), format="parquet", partitioning="hive")
    for frag in dset.get_fragments():
        t = frag.to_table(columns=["cell_id", "date", "sst", "clim", "thresh", "category"])
        cid = t["cell_id"].to_numpy()
        di = t["date"].cast(pa.int32()).to_numpy() - epoch0
        r, c = cid // 1440 - R0, cid % 1440 - C0
        sst[di, r, c] = t["sst"].to_numpy()
        clim[di, r, c] = t["clim"].to_numpy()
        thr[di, r, c] = t["thresh"].to_numpy()
        cat[di, r, c] = t["category"].to_numpy()
    return sst, clim, thr, cat


# ------------------------------------------------------------------ helpers (axis 0 = time)
def trailing_mean(a, w):
    cs = np.cumsum(np.nan_to_num(a, nan=0.0), axis=0, dtype=np.float64)
    out = np.full(a.shape, np.nan, np.float32)
    out[w - 1:] = (cs[w - 1:] - np.concatenate([np.zeros((1,) + a.shape[1:]), cs[:-w]])) / w
    return out


def lag(a, k):
    out = np.full(a.shape, np.nan, np.float32)
    out[k:] = a[:-k]
    return out


def lead_window_any(flag, h):
    """1 if flag is set on any of the next h days (t+1 .. t+h)."""
    cs = np.cumsum(flag, axis=0, dtype=np.int32)
    out = np.zeros(flag.shape, np.int8)
    out[:-h] = (cs[h:] - cs[:-h]) > 0
    return out


def run_length(flag):
    """Consecutive days with flag set, ending on day t (0 if not set)."""
    out = np.zeros(flag.shape, np.int16)
    prev = np.zeros(flag.shape[1:], np.int16)
    for t in range(flag.shape[0]):
        prev = np.where(flag[t], np.minimum(prev + 1, 999), 0).astype(np.int16)
        out[t] = prev
    return out


def days_since(flag, cap=365):
    out = np.zeros(flag.shape, np.int16)
    prev = np.full(flag.shape[1:], cap, np.int16)
    for t in range(flag.shape[0]):
        prev = np.where(flag[t], 0, np.minimum(prev + 1, cap)).astype(np.int16)
        out[t] = prev
    return out


def spatial_mean(a, k, ocean, exclude_centre=False):
    """Mean of a over the k×k window of ocean cells around each cell, per day (ring without the centre if asked)."""
    a0 = np.nan_to_num(a, nan=0.0).astype(np.float32)
    if exclude_centre:
        w = np.ones((1, k, k), np.float32)
        w[0, k // 2, k // 2] = 0
        num = ndimage.convolve(a0, w, mode="constant")
        den = ndimage.convolve(ocean.astype(np.float32)[None], w, mode="constant")[0]
    else:   # separable box filter: much faster for large windows (window means; their ratio is the same)
        num = ndimage.uniform_filter(a0, size=(1, k, k), mode="constant", output=np.float32)
        den = ndimage.uniform_filter(ocean.astype(np.float32), size=(k, k), mode="constant", output=np.float32)
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(den > 0, num / den, np.nan).astype(np.float32)


def window_ahead_min(a, h):
    """min(a[t+1 .. t+h]) for each t (NaN for the last h days)."""
    out = np.full(a.shape, np.nan, np.float32)
    m = a[1:T - h + 1].copy()
    for k in range(2, h + 1):
        np.minimum(m, a[k:T - h + k], out=m)
    out[:T - h] = m
    return out


def window_back_max(a, w):
    """max(a[t-w+1 .. t]) for each t."""
    out = a.copy()
    for k in range(1, w):
        out[k:] = np.fmax(out[k:], a[:-k])
    return out


# ------------------------------------------------------------------ main
def main():
    log("loading lake")
    sst, clim, thr, cat = load()
    ocean = ~np.isnan(sst[0])
    log(f"grid {sst.shape}, ocean cells {ocean.sum()}")
    years = DATES.astype("datetime64[Y]").astype(int) + 1970
    months = DATES.astype("datetime64[M]").astype(int) % 12 + 1

    anom = sst - clim
    gap = thr - clim
    ratio = np.where(gap > 0, anom / gap, np.nan).astype(np.float32)
    exceed = (sst > thr) & ocean[None]
    in_mhw = cat > 0
    mhw_run = run_length(in_mhw)                       # day number within the (retrospective) event
    confirmed = in_mhw & (mhw_run >= 5)                # known in real time: the run has already lasted 5 days
    label = lead_window_any(in_mhw, HORIZON)           # in a heatwave on any of the next 7 days

    # Rows: the new ("operational") task keeps every cell-day not in a confirmed heatwave; the old task keeps
    # only cell-days with category 0 (decided with hindsight). Old rows are a subset of new rows.
    tvalid = np.zeros(T, bool)
    tvalid[30:T - HORIZON] = True
    rows = (~confirmed) & ocean[None] & tvalid[:, None, None]
    idx = np.flatnonzero(rows)
    t_of = idx // (NR * NC)
    yr = years[t_of]
    lab = label.ravel()[idx].astype(np.int8)
    old_task = (cat.ravel()[idx] == 0)
    # sampling: fit years thinned (all positives 50%, negatives 6%); val and test 30% uniform
    u = rng.random(len(idx))
    fit = (yr <= 2014) & (u < np.where(lab == 1, 0.5, 0.06))
    val = (yr >= 2015) & (yr <= 2018) & (u < 0.3)
    test = (yr >= 2019) & (u < 0.3)
    keep = fit | val | test
    idx, t_of, yr, lab, old_task = idx[keep], t_of[keep], yr[keep], lab[keep], old_task[keep]
    split = np.where(fit[keep], "fit", np.where(val[keep], "val", "test"))
    log(f"rows: fit {np.sum(split == 'fit'):,}, val {np.sum(split == 'val'):,}, test {np.sum(split == 'test'):,}; "
        f"old-task share {old_task.mean():.3f}")
    del rows, u, keep
    F = {}

    def put(name, arr):
        F[name] = np.asarray(arr).ravel()[idx].astype(np.float32)

    # --- current Spark features (mhw_days_90 and nb_mhw_frac use the retrospective heatwave flag)
    put("anomaly", anom); put("ratio", ratio)
    put("anom_7", trailing_mean(anom, 7)); put("anom_30", trailing_mean(anom, 30))
    for k in (1, 3, 7):
        put(f"trend_{k}", anom - lag(anom, k))
    put("mhw_days_90", trailing_mean(in_mhw.astype(np.float32), 90) * 90)
    nb3 = spatial_mean(anom, 3, ocean, exclude_centre=True)
    put("nb_anom", nb3)
    put("nb_mhw_frac", spatial_mean(in_mhw.astype(np.float32), 3, ocean, exclude_centre=True))
    m = months[t_of]
    F["month_sin"], F["month_cos"] = np.sin(2 * np.pi * m / 12).astype(np.float32), np.cos(2 * np.pi * m / 12).astype(np.float32)
    rr, cc = np.unravel_index(idx % (NR * NC), (NR, NC))
    F["lat"] = (-90 + (R0 + rr + 0.5) * 0.25).astype(np.float32)
    F["lon"] = ((C0 + cc + 0.5) * 0.25).astype(np.float32)
    cm = climate.climate_monthly(cfg.aux("dmi.txt"), cfg.aux("oni.txt")).set_index(["year", "month"])
    ym = pd.MultiIndex.from_arrays([yr, m])
    F["dmi"] = cm["dmi"].reindex(ym).to_numpy(np.float32); F["oni"] = cm["oni"].reindex(ym).to_numpy(np.float32)
    # one-month lag: the monthly indices are published after the month ends
    pm = pd.MultiIndex.from_arrays([np.where(m == 1, yr - 1, yr), np.where(m == 1, 12, m - 1)])
    F["dmi_lag1"] = cm["dmi"].reindex(pm).to_numpy(np.float32); F["oni_lag1"] = cm["oni"].reindex(pm).to_numpy(np.float32)
    log("current features done")

    # --- real-time replacements and new candidates
    ex = exceed.astype(np.float32)
    put("exceed_days_90", trailing_mean(ex, 90) * 90)
    put("nb_exceed", spatial_mean(ex, 3, ocean, exclude_centre=True))
    put("nb_confirmed", spatial_mean(confirmed.astype(np.float32), 3, ocean, exclude_centre=True))
    put("run_len", run_length(exceed)); put("days_since_exceed", days_since(exceed))
    put("max_anom_7", window_back_max(anom, 7))
    for k in (7, 21):
        nbk = spatial_mean(anom, k, ocean)
        put(f"nb_anom_{k}", nbk)
        if k == 7:
            put("nb_trend_3", nbk - lag(nbk, 3))
        del nbk
        put(f"nb_exceed_{k}", spatial_mean(ex, k, ocean))
    put("nb_ratio", spatial_mean(ratio, 3, ocean, exclude_centre=True))
    put("nb_ratio_7", spatial_mean(ratio, 7, ocean))
    put("ratio_7", trailing_mean(ratio, 7)); put("ratio_30", trailing_mean(ratio, 30))
    put("ratio_trend_3", ratio - lag(ratio, 3))
    put("exceed_days_30", trailing_mean(ex, 30) * 30)
    put("nb_ratio_21", spatial_mean(ratio, 21, ocean))
    put("ratio_max_7", window_back_max(ratio, 7))
    rmax = ndimage.maximum_filter(np.nan_to_num(ratio, nan=-9.0), size=(1, 7, 7), mode="constant", cval=-9.0)
    put("nb_ratio_max_7", np.where(ocean[None], rmax, np.nan)); del rmax
    nbe7 = spatial_mean(ex, 7, ocean)
    put("nb_exceed_trend_3", nbe7 - lag(nbe7, 3)); del nbe7
    gc.collect()
    log("neighbour features done")
    # seasonal outlook from the fixed climatology (known in advance): warming needed to reach next week's threshold
    thr_min_ahead = window_ahead_min(thr, HORIZON)
    put("gap_to_thr_ahead", thr_min_ahead - sst)
    put("clim_tend_7", lead_minus(clim))
    put("thr_tend_7", lead_minus(thr))
    del thr_min_ahead
    reg = np.nanmean(anom.reshape(T, -1), axis=1).astype(np.float32)        # whole-region mean anomaly per day
    F["region_anom"] = reg[t_of]
    F["region_trend_7"] = (reg - np.concatenate([np.full(7, np.nan), reg[:-7]]))[t_of].astype(np.float32)
    F["region_exceed"] = (exceed.reshape(T, -1).sum(1) / ocean.sum())[t_of].astype(np.float32)
    log("all features done")
    del sst, clim, thr, cat, anom, gap, ratio, exceed, in_mhw, mhw_run, confirmed, label, ex, nb3
    gc.collect()

    X = pd.DataFrame(F)
    X["label"], X["split"], X["old_task"], X["year"] = lab, split, old_task, yr
    X.to_parquet(OUT / "lab_table.parquet")
    log(f"saved lab table {X.shape}")
    return X


def lead_minus(a):
    out = np.full(a.shape, np.nan, np.float32)
    out[:-HORIZON] = a[HORIZON:] - a[:-HORIZON]
    return out


CURRENT = ["anomaly", "ratio", "anom_7", "anom_30", "trend_1", "trend_3", "trend_7", "mhw_days_90", "nb_anom",
           "nb_mhw_frac", "month_sin", "month_cos", "lat", "lon", "dmi", "oni"]
REALTIME = [f if f not in ("mhw_days_90", "nb_mhw_frac", "dmi", "oni") else
            {"mhw_days_90": "exceed_days_90", "nb_mhw_frac": "nb_exceed", "dmi": "dmi_lag1", "oni": "oni_lag1"}[f]
            for f in CURRENT]
RUN = REALTIME + ["run_len", "days_since_exceed", "nb_confirmed"]
NBR = RUN + ["nb_anom_7", "nb_anom_21", "nb_exceed_7", "nb_exceed_21", "nb_trend_3", "nb_ratio"]
OUTLOOK = NBR + ["gap_to_thr_ahead", "clim_tend_7", "thr_tend_7"]
ALL = OUTLOOK + ["max_anom_7", "region_anom", "region_trend_7", "region_exceed"]

EXPERIMENTS = [
    ("E0 current features, hindsight rows", "old", CURRENT),
    ("E1 real-time features, hindsight rows", "old", REALTIME),
    ("E2 real-time features, operational rows", "new", REALTIME),
    ("E3 + run length above threshold", "new", RUN),
    ("E4 + multi-scale neighbours", "new", NBR),
    ("E5 + threshold outlook", "new", OUTLOOK),
    ("E6 + regional context", "new", ALL),
]


def best_f1(y, s):
    p, r, t = precision_recall_curve(y, s)
    f = 2 * p * r / np.maximum(p + r, 1e-9)
    i = np.nanargmax(f[:-1])
    return float(t[i])


def prf(y, s, thr):
    hit = s >= thr
    tp, fp, fn = np.sum(hit & (y == 1)), np.sum(hit & (y == 0)), np.sum(~hit & (y == 1))
    p, r = tp / max(tp + fp, 1), tp / max(tp + fn, 1)
    return p, r, 2 * p * r / max(p + r, 1e-9)


def run_experiments(X, params=None):
    params = params or dict(max_iter=500, learning_rate=0.06, max_leaf_nodes=63, min_samples_leaf=200,
                            l2_regularization=1.0, early_stopping=True, validation_fraction=0.1,
                            n_iter_no_change=25, random_state=0)
    res = []
    for task in ("old", "new"):
        D = X[X.old_task] if task == "old" else X
        v, te = D[D.split == "val"], D[D.split == "test"]
        res.append({"experiment": f"persistence (ratio), {task} rows", "task": task, "n_features": 1,
                    "val_ap": average_precision_score(v.label, v.ratio.fillna(-9)),
                    "test_ap": average_precision_score(te.label, te.ratio.fillna(-9)),
                    "test_rate": te.label.mean()})
        thr = best_f1(v.label.to_numpy(), v.ratio.fillna(-9).to_numpy())
        res[-1].update(dict(zip(("test_precision", "test_recall", "test_f1"), prf(te.label.to_numpy(), te.ratio.fillna(-9).to_numpy(), thr))))
        log(res[-1]["experiment"], f"val {res[-1]['val_ap']:.3f} test {res[-1]['test_ap']:.3f}")
    for name, task, feats in EXPERIMENTS:
        D = X[X.old_task] if task == "old" else X
        fit, v, te = D[D.split == "fit"], D[D.split == "val"], D[D.split == "test"]
        t0 = time.time()
        clf = HistGradientBoostingClassifier(**params).fit(fit[feats], fit.label)
        sv, st = clf.predict_proba(v[feats])[:, 1], clf.predict_proba(te[feats])[:, 1]
        thr = best_f1(v.label.to_numpy(), sv)
        p, r, f1 = prf(te.label.to_numpy(), st, thr)
        res.append({"experiment": name, "task": task, "n_features": len(feats),
                    "val_ap": average_precision_score(v.label, sv), "test_ap": average_precision_score(te.label, st),
                    "test_rate": te.label.mean(), "test_precision": p, "test_recall": r, "test_f1": f1,
                    "iterations": clf.n_iter_, "seconds": round(time.time() - t0, 1)})
        log(name, f"val {res[-1]['val_ap']:.3f} test {res[-1]['test_ap']:.3f} f1 {f1:.3f} ({res[-1]['seconds']} s)")
    out = pd.DataFrame(res)
    out.to_csv(OUT / "lab_results.csv", index=False)
    print(out.round(3).to_string(index=False))
    return out


# Round 2: features that mean the same thing in any decade (relative to the threshold), no absolute anomaly levels,
# location or calendar; early stopping on the validation years; optional recency weights and monotonic constraints.
STATIONARY = ["ratio", "ratio_7", "ratio_30", "ratio_trend_3", "trend_1", "trend_3", "trend_7", "run_len",
              "days_since_exceed", "exceed_days_30", "nb_ratio", "nb_ratio_7", "nb_exceed", "nb_exceed_7",
              "nb_exceed_21", "nb_confirmed", "gap_to_thr_ahead", "thr_tend_7", "clim_tend_7"]
INCREASING = {"ratio", "ratio_7", "run_len", "nb_ratio", "nb_ratio_7", "nb_exceed", "nb_exceed_7", "nb_exceed_21",
              "nb_confirmed"}
DECREASING = {"gap_to_thr_ahead", "days_since_exceed"}
V2 = [
    ("R1 all features (E6), val early stopping", ALL, {}),
    ("R2 threshold-relative features", STATIONARY, {}),
    ("R3 R2 + season", STATIONARY + ["month_sin", "month_cos"], {}),
    ("R4 R2 + monotonic constraints", STATIONARY, {"monotonic": True}),
    ("R5 R2 + recency weights", STATIONARY, {"recency": True}),
    ("R6 R4 + recency weights", STATIONARY, {"monotonic": True, "recency": True}),
]


def run_v2(X):
    D = X  # operational rows only
    fit, v, te = D[D.split == "fit"], D[D.split == "val"], D[D.split == "test"]
    res = []
    for name, feats, opt in V2:
        cst = [1 if f in INCREASING else (-1 if f in DECREASING else 0) for f in feats] if opt.get("monotonic") else None
        w = np.exp((fit.year.to_numpy() - 2014) / 10.0) if opt.get("recency") else None   # weight ~e-fold per decade
        clf = HistGradientBoostingClassifier(max_iter=600, learning_rate=0.05, max_leaf_nodes=31, min_samples_leaf=500,
                                             l2_regularization=1.0, early_stopping=True, scoring="average_precision",
                                             n_iter_no_change=30, monotonic_cst=cst, random_state=0)
        t0 = time.time()
        clf.fit(fit[feats], fit.label, sample_weight=w, X_val=v[feats], y_val=v.label)
        sv, st = clf.predict_proba(v[feats])[:, 1], clf.predict_proba(te[feats])[:, 1]
        p, r, f1 = prf(te.label.to_numpy(), st, best_f1(v.label.to_numpy(), sv))
        res.append({"experiment": name, "n_features": len(feats), "val_ap": average_precision_score(v.label, sv),
                    "test_ap": average_precision_score(te.label, st), "test_precision": p, "test_recall": r,
                    "test_f1": f1, "iterations": clf.n_iter_, "seconds": round(time.time() - t0, 1)})
        log(name, f"val {res[-1]['val_ap']:.3f} test {res[-1]['test_ap']:.3f} f1 {f1:.3f} it {clf.n_iter_}")
    out = pd.DataFrame(res)
    out.to_csv(OUT / "lab_results_round2.csv", index=False)
    print(out.round(3).to_string(index=False))
    return out


# Round 3: more "heatwave nearby" features, a little tuning, and the strict onset subset (water still below the
# threshold today, not in a confirmed heatwave): the label there is "a new heatwave starts within 7 days".
NEARBY = STATIONARY + ["nb_ratio_21", "ratio_max_7", "nb_ratio_max_7", "nb_exceed_trend_3"]
HGB = dict(max_iter=800, learning_rate=0.05, max_leaf_nodes=31, min_samples_leaf=500, l2_regularization=1.0,
           early_stopping=True, scoring="average_precision", n_iter_no_change=30, random_state=0)
V3 = [
    ("Q1 threshold-relative (R2)", STATIONARY, {}),
    ("Q2 + nearby-heatwave features", NEARBY, {}),
    ("Q3 Q2, bigger trees", NEARBY, {"max_leaf_nodes": 63, "min_samples_leaf": 1000, "learning_rate": 0.04}),
    ("Q4 Q2, smaller trees", NEARBY, {"max_leaf_nodes": 15, "min_samples_leaf": 300, "learning_rate": 0.08}),
]


def run_v3(X):
    fit, v, te = X[X.split == "fit"], X[X.split == "val"], X[X.split == "test"]
    on_v, on_te = (v.run_len == 0).to_numpy(), (te.run_len == 0).to_numpy()   # strict onset subset
    res = [{"experiment": "persistence (ratio)", "val_ap": average_precision_score(v.label, v.ratio),
            "test_ap": average_precision_score(te.label, te.ratio),
            "onset_test_ap": average_precision_score(te.label[on_te], te.ratio[on_te]),
            "onset_test_rate": te.label[on_te].mean()}]
    log(res[-1])
    for name, feats, opt in V3:
        clf = HistGradientBoostingClassifier(**{**HGB, **opt}).fit(fit[feats], fit.label, X_val=v[feats], y_val=v.label)
        sv, st = clf.predict_proba(v[feats])[:, 1], clf.predict_proba(te[feats])[:, 1]
        p, r, f1 = prf(te.label.to_numpy(), st, best_f1(v.label.to_numpy(), sv))
        res.append({"experiment": name, "n_features": len(feats), "val_ap": average_precision_score(v.label, sv),
                    "test_ap": average_precision_score(te.label, st), "test_f1": f1, "test_precision": p, "test_recall": r,
                    "onset_test_ap": average_precision_score(te.label[on_te], st[on_te]), "iterations": clf.n_iter_})
        log(name, {k: round(v_, 3) for k, v_ in res[-1].items() if isinstance(v_, float)})
    out = pd.DataFrame(res)
    out.to_csv(OUT / "lab_results_round3.csv", index=False)
    print(out.round(3).to_string(index=False))


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--round3":
        run_v3(main() if "--build" in sys.argv else pd.read_parquet(OUT / "lab_table.parquet"))
        sys.exit()
    if len(sys.argv) > 1 and sys.argv[1] == "--reuse":
        run_experiments(pd.read_parquet(OUT / "lab_table.parquet"))
    elif len(sys.argv) > 1 and sys.argv[1] == "--round2":
        run_v2(pd.read_parquet(OUT / "lab_table.parquet"))
    else:
        X = main()
        run_experiments(X)
        run_v2(X)
        run_v3(X)
