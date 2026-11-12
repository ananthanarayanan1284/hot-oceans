"""Unit tests for the heatwave core. Run: python -m pytest tests  (or: python tests/test_hobday.py)"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hot_oceans import events, grid, hobday  # noqa: E402


def synthetic(seed=0):
    dates = pd.date_range("1982-01-01", "2025-12-31", freq="D")
    rng = np.random.default_rng(seed)
    doy = dates.dayofyear.to_numpy()
    sst = 28.5 + 1.0 * np.cos(2 * np.pi * (doy - 125) / 365.25) + rng.normal(0, 0.15, len(dates))
    return dates, sst


def test_doy366_puts_29_feb_at_60():
    d = pd.DatetimeIndex(["2023-03-01", "2024-02-29", "2024-03-01", "2023-12-31"])
    assert list(hobday.doy366(d)) == [61, 60, 61, 366]


def test_climatology_shape_and_order():
    dates, sst = synthetic()
    seas, thr = hobday.climatology(dates, sst, "1991-01-01", "2020-12-31")
    assert seas.shape == thr.shape == (366,)
    assert np.all(thr > seas)


def test_detects_injected_heatwave_and_ignores_short_spike():
    dates, sst = synthetic()
    seas, thr = hobday.climatology(dates, sst, "1991-01-01", "2020-12-31")
    sst = sst.copy()
    hw = (dates >= "2024-04-10") & (dates <= "2024-05-09")      # 30-day, +2.5 °C heatwave
    spike = (dates >= "2010-08-01") & (dates <= "2010-08-03")   # 3-day spike: below min duration
    sst[hw] += 2.5
    sst[spike] += 2.5
    res = hobday.detect(dates, sst, seas, thr)
    assert res.loc[hw, "category"].min() >= 1
    assert res.loc[hw, "event_no"].nunique() == 1
    assert res.loc[spike, "category"].max() == 0
    assert res.loc[hw, "category"].max() >= 2                     # +2.5 °C is several threshold gaps


def test_gap_of_two_days_joins_events():
    dates, sst = synthetic(1)
    seas, thr = hobday.climatology(dates, sst, "1991-01-01", "2020-12-31")
    sst = sst.copy()
    a = (dates >= "2016-03-01") & (dates <= "2016-03-08")
    b = (dates >= "2016-03-11") & (dates <= "2016-03-18")
    sst[a | b] += 2.0
    res = hobday.detect(dates, sst, seas, thr)
    assert res.loc[a | b, "event_no"].nunique() == 1


def test_grid_dbscan_core_border_noise():
    # 3x3 block (all core), one border cell touching it, one isolated cell (noise).
    rows = [0, 0, 0, 1, 1, 1, 2, 2, 2, 3, 9]
    cols = [0, 1, 2, 0, 1, 2, 0, 1, 2, 3, 9]
    labels = events.cluster_day(rows, cols, eps=1.5, min_samples=4)
    assert len(set(labels[:9])) == 1 and labels[0] >= 0
    assert labels[9] == labels[0]          # (3,3) touches core (2,2) diagonally -> border point
    assert labels[10] == -1                # isolated cell -> noise


def test_cluster_and_link():
    rows = np.array([10, 10, 11, 11, 50, 50, 51, 51])
    cols = np.array([10, 11, 10, 11, 50, 51, 50, 51])
    labels = events.cluster_day(rows, cols, eps=1.5, min_samples=3)
    assert len(set(labels[:4])) == 1 and len(set(labels[4:])) == 1 and labels[0] != labels[4]
    idx = events.link(["a", "b", "c", "d"], [("a", "b"), ("b", "c")])
    assert idx["a"] == idx["c"] != idx["d"]


def test_grid_roundtrip():
    lat, lon = 10.625, 72.625
    cid = grid.cell_id(lat, lon)
    la, lo = grid.center(cid)
    assert abs(la - lat) < 1e-9 and abs(lo - lon) < 1e-9


def test_cell_features_use_only_the_past_and_confirm_on_day_5():
    from pipeline.features import cell_features
    dates = pd.date_range("2000-01-01", "2001-12-31", freq="D")
    n = len(dates)
    clim, thr = np.full(n, 28.0), np.full(n, 29.0)
    sst = np.full(n, 28.5)
    ev = (dates >= "2000-06-10") & (dates <= "2000-06-17")      # 8-day heatwave: SST above the threshold
    sst[ev] = 29.5
    cat = np.where(ev, 1, 0)
    pdf = pd.DataFrame({"cell_id": 1, "date": dates.date, "sst": sst, "clim": clim, "thresh": thr,
                        "ratio": (sst - clim) / (thr - clim), "category": cat})
    out = cell_features(pdf).set_index(pd.DatetimeIndex(dates))
    assert out.loc["2000-06-13", "confirmed"] == 0 and out.loc["2000-06-14", "confirmed"] == 1   # day 4 vs day 5
    assert out.loc["2000-06-12", "run_len"] == 3 and out.loc["2000-06-09", "run_len"] == 0
    assert out.loc["2000-06-09", "label"] == 1 and out.loc["2000-06-03", "label"] == 1   # heatwave within 7 days
    assert out.loc["2000-06-02", "label"] == 0                                            # 8 days ahead: no
    assert out.loc["2000-06-20", "days_since_exceed"] == 3
    assert abs(out.loc["2000-06-01", "gap_to_thr_ahead"] - 0.5) < 1e-6    # threshold 29.0 vs SST 28.5
    assert np.isnan(out["label"].iloc[-1])                                # no future data at the end


def test_features_do_not_change_when_the_future_is_removed():
    """Leakage test: recompute detection and features from data cut off at day t; inputs at t must not change."""
    from pipeline.features import CELL_FEATURES, cell_features
    dates, sst = synthetic(3)
    seas, thr = hobday.climatology(dates, sst, "1991-01-01", "2020-12-31")
    sst = sst.copy()
    # Two warm runs joined across a 2-day gap (the gap days are a heatwave only because the second run lasts 5 days).
    for a, b in (("2021-03-01", "2021-03-08"), ("2021-03-11", "2021-03-18"), ("2022-07-01", "2022-07-03")):
        sst[(dates >= a) & (dates <= b)] += 2.0
    det = hobday.detect(dates, sst, seas, thr)
    df = pd.DataFrame({"cell_id": 1, "date": dates.date, "sst": sst, "clim": det.clim, "thresh": det.thresh,
                       "ratio": det.ratio, "category": det.category})
    full = cell_features(df)
    days = pd.date_range("2021-02-25", "2021-03-25").append(pd.date_range("2022-06-28", "2022-07-06"))
    for day in days:
        i = int(np.searchsorted(dates, day))
        cut = df.iloc[:i + 1].copy()
        cut["category"] = hobday.detect(dates[:i + 1], sst[:i + 1], seas, thr)["category"].to_numpy()
        a, b = full.iloc[i], cell_features(cut).iloc[i]
        for col in CELL_FEATURES + ["exceed", "confirmed"]:
            x, y = float(a[col]), float(b[col])
            assert (np.isnan(x) and np.isnan(y)) or abs(x - y) < 1e-5, (day.date(), col, x, y)
    gap_day = int(np.searchsorted(dates, pd.Timestamp("2021-03-09")))
    assert det.category.iloc[gap_day] > 0 and full.confirmed.iloc[gap_day] == 0   # hindsight says heatwave; real time not yet


def test_neighbour_features():
    from pipeline.features import neighbours_for_day
    # 3x3 block; the centre's 8 neighbours have ratio 1.0, two of them above the threshold, one confirmed.
    base = grid.cell_id(10.125, 72.125)
    cids = [base + dr * 1440 + dc for dr in (-1, 0, 1) for dc in (-1, 0, 1)]
    pdf = pd.DataFrame({"cell_id": cids, "date": pd.Timestamp("2023-05-01"),
                        "ratio": [1.0] * 4 + [5.0] + [1.0] * 4, "exceed": [1, 1, 0, 0, 0, 0, 0, 0, 0],
                        "confirmed": [1, 0, 0, 0, 0, 0, 0, 0, 0]})
    out = neighbours_for_day(pdf).set_index("cell_id")
    assert abs(out.loc[base, "nb_ratio"] - 1.0) < 1e-6
    assert abs(out.loc[base, "nb_exceed"] - 2 / 8) < 1e-6 and abs(out.loc[base, "nb_confirmed"] - 1 / 8) < 1e-6
    corner = cids[0]                       # 3 neighbours: ratios 1, 1, 5 -> mean 7/3; one above threshold of three
    assert abs(out.loc[corner, "nb_ratio"] - 7 / 3) < 1e-5
    assert abs(out.loc[corner, "nb_exceed"] - 1 / 3) < 1e-6
    assert abs(out.loc[corner, "nb_ratio_max_7"] - 5.0) < 1e-6
    assert abs(out.loc[base, "nb_ratio_7"] - 13 / 9) < 1e-5   # all 9 cells inside the 7x7 window


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok  {name}")
