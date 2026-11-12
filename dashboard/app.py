"""Hot Oceans dashboard (Streamlit + pydeck). Reads only the small files from pipeline.export_dashboard.

Run on the PC:  streamlit run dashboard/app.py -- --mode full
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hot_oceans.config import load  # first: sets Windows env fixes before numpy is used

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import pydeck as pdk  # noqa: E402
import streamlit as st  # noqa: E402

CAT = {1: ("Moderate", [227, 138, 30]), 2: ("Strong", [207, 83, 28]), 3: ("Severe", [163, 35, 27]), 4: ("Extreme", [94, 18, 20])}
VIEW = pdk.ViewState(latitude=0, longitude=75, zoom=2.6)

# --mode dev|full on the command line; otherwise HOT_OCEANS_MODE; otherwise the full basin (e.g. on Streamlit Cloud)
mode = sys.argv[sys.argv.index("--mode") + 1] if "--mode" in sys.argv else (os.environ.get("HOT_OCEANS_MODE") or "full")
cfg = load(env="pc", mode=mode)
D = cfg.out("dashboard")
st.set_page_config(page_title="Hot Oceans", layout="wide")


@st.cache_data
def read(name):
    p = D / name
    if not p.exists():
        return None
    if p.suffix == ".parquet":
        return pd.read_parquet(p)
    if p.suffix == ".csv":
        return pd.read_csv(p)
    return json.loads(p.read_text())


@st.cache_data
def read_by_date(name):
    """Rows sorted by date, so one day is a slice (the full-ocean file has ~12 million rows)."""
    d = read(name)
    if d is None:
        return None
    return d.assign(date=pd.to_datetime(d.date)).sort_values("date", kind="stable").reset_index(drop=True)


@st.cache_data
def read_events():
    p = D / "events.geojson"
    if not p.exists():
        return None
    import geopandas as gpd
    return gpd.read_file(p).sort_values("cum_intensity", ascending=False).reset_index(drop=True)


def on_day(d, day):
    t = np.datetime64(day)
    return d.iloc[d.date.searchsorted(t):d.date.searchsorted(t, side="right")]


def day_options(d):
    return list(pd.DatetimeIndex(d.date.unique()).date)


cells, daily = read("cells.parquet"), read_by_date("daily_cat.parquet")
if cells is None or daily is None:
    st.error(f"No dashboard files in {D}. Run pipeline.export_dashboard and copy outputs/ from the DGX.")
    st.stop()

st.title("Hot Oceans")
st.caption("Marine heatwaves across the Indian Ocean · NOAA OISST v2.1, 0.25° daily, 1982–2025 · baseline 1991–2020")

dates = day_options(daily)
c1, c2 = st.columns([3, 1])
day = c1.select_slider("Date", options=dates, value=dates[min(len(dates) - 1, len(dates) // 2)])
min_cat = c2.selectbox("Show", [1, 2, 3, 4], format_func=lambda c: f"{CAT[c][0]} and above")

tab_map, tab_events, tab_trends, tab_risk, tab_case, tab_model = st.tabs(
    ["Heatwave map", "Events", "Trends & drivers", "Week-ahead risk", "Lakshadweep 2023–24", "Model & rules"])

with tab_map:
    today = on_day(daily, day)
    today = today[today.category >= min_cat].merge(cells, on="cell_id")
    today["color"] = today.category.map(lambda c: CAT[c][1])
    today["label"] = today.category.map(lambda c: CAT[c][0])
    ocean_area = cells.area_km2.sum()
    k1, k2, k3 = st.columns(3)
    k1.metric("Ocean area in a heatwave", f"{today.area_km2.sum() / ocean_area:.1%}")
    k2.metric("Strongest category", CAT[int(today.category.max())][0] if len(today) else "None")
    k3.metric("Mean anomaly in heatwave cells", f"{today.anomaly.mean():+.2f} °C" if len(today) else "–")
    layer = pdk.Layer("GridCellLayer", today.assign(lon0=today.lon - 0.125, lat0=today.lat - 0.125),
                      get_position=["lon0", "lat0"], cell_size=27800, get_fill_color="color", pickable=True)
    st.pydeck_chart(pdk.Deck(layers=[layer], initial_view_state=VIEW, map_style=None,
                             tooltip={"text": "{label}\n{anomaly} °C anomaly\n{lat}, {lon}"}))

@st.cache_data
def read_event_footprints():
    return read("event_footprints.parquet")


@st.cache_data
def ocean_mask():
    """0.25° ocean/land grid of the study box, for the background of the event map."""
    r = np.round((cells.lat.to_numpy() - cells.lat.min()) / 0.25).astype(int)
    c = np.round((cells.lon.to_numpy() - cells.lon.min()) / 0.25).astype(int)
    m = np.zeros((r.max() + 1, c.max() + 1), bool)
    m[r, c] = True
    return m, [cells.lon.min() - 0.125, cells.lon.max() + 0.125, cells.lat.min() - 0.125, cells.lat.max() + 0.125]


LONG_EVENT_DAYS = 120   # longer events are chains of many patches: show where they were, not a track


def _event_axes(geoms, figsize=(6.4, 5.0)):
    """Figure with the ocean/land background, zoomed to the given geometries."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import shapely
    from matplotlib.colors import ListedColormap

    x0, y0, x1, y1 = shapely.total_bounds(geoms)
    mask, full = ocean_mask()
    ext = [max(full[0], x0 - 3), min(full[1], x1 + 3), max(full[2], y0 - 3), min(full[3], y1 + 3)]
    fig, ax = plt.subplots(figsize=figsize)
    ax.imshow(np.where(mask, 1.0, np.nan), extent=full, origin="lower", cmap=ListedColormap(["#f3f6fa"]),
              interpolation="nearest", zorder=0)
    ax.imshow(np.where(mask, np.nan, 1.0), extent=full, origin="lower", cmap=ListedColormap(["#dedbd2"]),
              interpolation="nearest", zorder=3)
    ax.set_xlim(ext[0], ext[1]); ax.set_ylim(ext[2], ext[3]); ax.set_aspect("equal")
    ax.xaxis.set_major_formatter(lambda v, _: f"{v:.0f}°E")
    ax.yaxis.set_major_formatter(lambda v, _: f"{abs(v):.0f}°{'N' if v > 0 else 'S' if v < 0 else ''}")
    ax.tick_params(colors="#52514e", labelsize=8)
    for s in ax.spines.values():
        s.set_edgecolor("#c3c2b7")
    return fig, ax, plt


def _colorbar(fig, ax, plt, cmap, norm, label):
    cb = fig.colorbar(plt.cm.ScalarMappable(cmap=cmap, norm=norm), ax=ax, fraction=0.035, pad=0.03, shrink=0.8)
    cb.set_label(label, fontsize=8, color="#52514e")
    cb.ax.tick_params(labelsize=7.5, colors="#52514e"); cb.outline.set_edgecolor("#c3c2b7")


def event_track_figure(row, days):
    """Daily footprints coloured by day of the event, plus the centroid track (same picture as the report)."""
    import shapely
    from matplotlib.colors import ListedColormap
    from shapely import wkt

    ink, orange = "#0b0b0b", "#eb6834"
    geoms = shapely.from_wkb(days.wkb.to_numpy())
    day_no = (pd.to_datetime(days.date) - pd.to_datetime(days.date).min()).dt.days.to_numpy()
    fig, ax, plt = _event_axes(geoms)
    ramp = ListedColormap(["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"])
    norm = plt.Normalize(0, max(day_no.max(), 1))
    step = max(1, int(np.ceil(len(set(day_no)) / 15)))    # at most ~15 outlines per map
    for g, k in zip(geoms, day_no):
        if k % step == 0 or k == day_no.max():
            for poly in getattr(g, "geoms", [g]):
                xs, ys = poly.exterior.xy
                ax.plot(xs, ys, color=ramp(norm(k)), lw=0.9, zorder=2)
    if row.track_wkt:
        tr = np.array(wkt.loads(row.track_wkt).coords)
        ax.plot(tr[:, 0], tr[:, 1], color=orange, lw=1.8, zorder=5)
        ax.plot(*tr[0], marker="o", ms=8, color=orange, mec="white", zorder=6)
        ax.plot(*tr[-1], marker="s", ms=8, color=ink, mec="white", zorder=6)
    _colorbar(fig, ax, plt, ramp, norm, "Day of the event")
    every = "every day" if step == 1 else f"every {step} days"
    s, e = pd.Timestamp(row.start), pd.Timestamp(row.end)
    ax.legend(handles=[plt.Line2D([], [], color="#3987e5", lw=1, label=f"Daily footprint ({every})"),
                       plt.Line2D([], [], color=orange, lw=1.8, label="Centroid track"),
                       plt.Line2D([], [], color=orange, marker="o", lw=0, label=f"Start {s:%d %b %Y}"),
                       plt.Line2D([], [], color=ink, marker="s", lw=0, label=f"End {e:%d %b %Y}")],
              loc="best", fontsize=7.5, frameon=True, framealpha=0.92, edgecolor="none")
    ax.set_title(f"How {row.event_id} moved", fontsize=10, fontweight="bold", color=ink)
    return fig


@st.cache_data
def days_inside(event_id):
    """For one event: number of days each ocean cell lay inside one of the event's daily footprints."""
    import shapely
    fps = read_event_footprints()
    days = fps[fps.event_id == event_id]
    geoms = shapely.from_wkb(days.wkb.to_numpy())
    pts = shapely.points(cells.lon.to_numpy(), cells.lat.to_numpy())
    g_idx, p_idx = shapely.STRtree(pts).query(geoms, predicate="contains")
    day = pd.to_datetime(days.date).to_numpy()[g_idx]
    pairs = pd.DataFrame({"day": day, "cell": p_idx}).drop_duplicates()   # count each cell once per day
    return np.bincount(pairs.cell.to_numpy(), minlength=len(cells))


def event_coverage_figure(row, days):
    """Long events: map of how many days each 0.25° cell was inside the event (no centroid track)."""
    import shapely
    from matplotlib.colors import ListedColormap

    count = days_inside(row.event_id)
    geoms = shapely.from_wkb(days.wkb.to_numpy())
    fig, ax, plt = _event_axes(geoms)
    mask, full = ocean_mask()
    grid_ = np.full(mask.shape, np.nan)
    r = np.round((cells.lat.to_numpy() - cells.lat.min()) / 0.25).astype(int)
    c = np.round((cells.lon.to_numpy() - cells.lon.min()) / 0.25).astype(int)
    grid_[r, c] = np.where(count > 0, count, np.nan)
    heat = ListedColormap(["#fdeee4", "#fbd5bd", "#f7b48e", "#f08f5f", "#e26a37", "#c64f1f", "#9c3a14", "#6e280d"])
    norm = plt.Normalize(1, max(int(np.nanmax(grid_)), 2))
    ax.imshow(grid_, extent=full, origin="lower", cmap=heat, norm=norm, interpolation="nearest", zorder=1)
    _colorbar(fig, ax, plt, heat, norm, "Days inside the event")
    s, e = pd.Timestamp(row.start), pd.Timestamp(row.end)
    ax.set_title(f"Where {row.event_id} was ({s:%b %Y} – {e:%b %Y})", fontsize=10, fontweight="bold", color="#0b0b0b")
    return fig


def event_deck(row):
    """Interactive map: peak-day footprint and centroid track, centred on the event."""
    import geopandas as gpd
    from shapely import wkt
    layers = [pdk.Layer("GeoJsonLayer", json.loads(gpd.GeoSeries([row.geometry]).to_json()),
                        get_fill_color=[207, 83, 28, 90], get_line_color=[207, 83, 28], line_width_min_pixels=1)]
    if row.track_wkt:
        path = [list(c) for c in wkt.loads(row.track_wkt).coords]
        layers.append(pdk.Layer("PathLayer", [{"path": path}], get_path="path", get_color=[10, 79, 107],
                                width_min_pixels=3))
    long_ = row.duration_days > LONG_EVENT_DAYS
    c = row.geometry.centroid
    view = VIEW if long_ else pdk.ViewState(latitude=c.y, longitude=c.x, zoom=3.2)
    return pdk.Deck(layers=layers, initial_view_state=view, map_style=None)


with tab_events:
    ev = read_events()
    if ev is not None:
        from shapely import wkt
        st.dataframe(ev.drop(columns=["geometry", "track_wkt"]), width="stretch", hide_index=True)
        ids = list(ev.event_id)
        # default: a clean example (62 days, moves 8° south-west); a link can choose one with ?event=E-2023-028
        start_id = st.query_params.get("event", "E-2023-123")
        pick = st.selectbox("Event (type an ID, e.g. E-2018-183)", ids,
                            index=ids.index(start_id) if start_id in ids else 0)
        row = ev[ev.event_id == pick].iloc[0]
        long_event = row.duration_days > LONG_EVENT_DAYS
        moved = 0.0
        if row.track_wkt:
            tr = np.array(wkt.loads(row.track_wkt).coords)
            moved = float(np.hypot(*(tr[-1] - tr[0])))
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Duration", f"{int(row.duration_days)} days")
        m2.metric("Peak area", f"{row.peak_area_km2 / 1e3:,.0f} thousand km²")
        m3.metric("Strongest category", CAT[int(row.max_category)][0])
        m4.metric("Centroid moved", "not meaningful" if long_event else f"{moved:.1f}°",
                  help="For long events the centroid is an average of patches far apart, so it jumps around.")
        if long_event:
            st.caption(f"This event lasted more than {LONG_EVENT_DAYS} days. Long events are chains of many separate "
                       "hot patches (any overlap on consecutive days joins them), so instead of a track the right "
                       "map shows how many days each area was inside the event.")
        left, right = st.columns(2)
        with left:
            st.markdown("**Peak day and track (interactive map)**")
            st.pydeck_chart(event_deck(row), height=480)
        with right:
            fps = read_event_footprints()
            if fps is None:
                st.info("No event_footprints.parquet yet (run: python -m pipeline.export_event_footprints --mode full).")
            else:
                days = fps[fps.event_id == pick]
                if days.empty:
                    st.info("No footprints stored for this event.")
                else:
                    import matplotlib.pyplot as plt
                    st.markdown("**Days inside the event**" if long_event else "**Daily footprints and track**")
                    fig = event_coverage_figure(row, days) if long_event else event_track_figure(row, days)
                    st.pyplot(fig)
                    plt.close(fig)
with tab_trends:
    yearly = read("mhw_days_per_year.parquet")
    if yearly is not None:
        st.subheader("Heatwave days per year (mean per ocean cell)")
        st.bar_chart(yearly.set_index("year"))
    for name, title in (("regime_by_iod_phase.csv", "Regime share by Indian Ocean Dipole phase"),
                        ("regime_profiles.csv", "Regime profiles (K-Means)")):
        t = read(name)
        if t is not None:
            st.subheader(title)
            st.dataframe(t, width="stretch")

metrics = read("model_metrics.json")
best = metrics.get("best_model", "gbt") if metrics else None
warn_thr = metrics[best]["threshold_best_f1_val"] if metrics else 0.5

with tab_risk:
    risk = read_by_date("risk.parquet")
    if risk is None:
        st.info("No risk file yet (run Stage E, then export).")
    else:
        st.caption(f"Chance that each cell is in a heatwave within the next 7 days ({best.upper() if best else ''} model). "
                   "Cells already in a confirmed heatwave (5+ days above the threshold) are not scored and stay blank.")
        rdays = day_options(risk)
        rday = st.select_slider("Forecast day", options=rdays, value=rdays[-1])
        r = on_day(risk, rday).merge(cells, on="cell_id")
        warned = r.p_onset >= warn_thr
        k1, k2, k3 = st.columns(3)
        k1.metric("Cells scored", f"{len(r):,}")
        k2.metric(f"Cells warned (risk ≥ {warn_thr:.2f})", f"{int(warned.sum()):,}")
        k3.metric("Ocean area warned", f"{r.area_km2[warned].sum() / cells.area_km2.sum():.1%}")
        r["color"] = r.p_onset.map(lambda p: [207, 83, 28, int(30 + 225 * min(p, 1.0))])
        r["risk"] = (r.p_onset * 100).round(0).astype(int).astype(str) + "%"
        st.pydeck_chart(pdk.Deck(layers=[pdk.Layer("GridCellLayer", r.assign(lon0=r.lon - 0.125, lat0=r.lat - 0.125),
                                                   get_position=["lon0", "lat0"], cell_size=27800,
                                                   get_fill_color="color", pickable=True)],
                                 initial_view_state=VIEW, map_style=None,
                                 tooltip={"text": "Risk of a heatwave within 7 days: {risk}\n{lat}, {lon}"}))

with tab_case:
    cs, summary = read("case_study.parquet"), read("case_study_summary.json")
    if cs is not None:
        if summary:
            a, b, c = st.columns(3)
            a.metric("Heatwave began", summary["first_heatwave_day"])
            b.metric("Model first warned", summary["first_warning_day"])
            c.metric("Lead time (days)", summary["lead_days"])
        cs = cs.assign(date=pd.to_datetime(cs.date)).set_index("date")
        st.subheader("Sea surface temperature at Lakshadweep (°C)")
        st.line_chart(cs[["sst", "thresh", "clim"]].rename(columns={"sst": "SST", "thresh": "Heatwave threshold",
                                                                     "clim": "Climatology"}))
        st.subheader("Model risk before the May 2023 heatwave")
        win = cs.loc["2023-04-25":"2023-05-20", ["p_onset"]].rename(columns={"p_onset": "Risk"})
        st.line_chart(win.assign(**{"Warning threshold": warn_thr}))
        st.caption("The risk is blank once the heatwave is confirmed (5 days above the threshold).")

with tab_model:
    fi, rules = read("feature_importance.csv"), read("rules.csv")
    trust, by_year, by_region = read("trust_checks.json"), read("trust_by_year.csv"), read("trust_by_region.csv")
    if metrics:
        st.subheader("Week-ahead warning: test years 2019–2025 (never seen in training)")
        rows = [("Random guess", metrics["test_positive_rate"], metrics["onset_test_positive_rate"], None, None, None, None)]
        base = metrics["persistence_baseline"]
        rows.append(("Persistence rule (today's heat)", base["pr_auc_test"], base["pr_auc_onset_test"], None,
                     base["precision"], base["recall"], base["f1"]))
        for k, name in (("random_forest", "Random Forest"), ("gbt", "Gradient-Boosted Trees")):
            m, t = metrics[k], metrics[k]["test_at_threshold"]
            rows.append((name + (" (chosen)" if k == best else ""), m["pr_auc_test"], m["pr_auc_onset_test"],
                         m["roc_auc_test"], t["precision"], t["recall"], t["f1"]))
        st.dataframe(pd.DataFrame(rows, columns=["Method", "PR-AUC", "PR-AUC (below threshold today)", "ROC-AUC",
                                                 "Precision", "Recall", "F1"]).round(3),
                     width="stretch", hide_index=True)
        st.caption(f"{metrics['test_rows']:,} test cell-days, {metrics['test_positive_rate']:.1%} positive. "
                   "PR-AUC is the main score: a random guess scores the positive rate.")
    if trust:
        st.subheader("Can the warning be trusted?")
        bs, cal, lt = trust["bootstrap"], trust["calibration"], trust["lead_times"]
        a, b, c, d = st.columns(4)
        a.metric("Test years model wins", trust["years_model_better"])
        b.metric("Regions model wins", trust["regions_model_better"])
        c.metric("Gain over rule (95% CI)", f"+{bs['difference_ci95'][0]:.3f} to +{bs['difference_ci95'][1]:.3f}")
        d.metric("Calibration error", f"{cal['ece_calibrated']:.1%}", f"{cal['ece_calibrated'] - cal['ece_raw']:+.1%} after calibration",
                 delta_color="inverse")
        e, f, g, h = st.columns(4)
        if metrics and "pr_auc_spatial_cv_mean" in metrics.get(best, {}):
            e.metric("Unseen regions (spatial CV)", f"{metrics[best]['pr_auc_spatial_cv_mean']:.3f}")
        f.metric("Onsets warned ≥ 3 days ahead", f"{lt['model']['warned_3d_or_more_share']:.0%}",
                 f"{lt['model']['warned_3d_or_more_share'] - lt['rule']['warned_3d_or_more_share']:+.0%} vs rule")
        g.metric("Median lead when warned", f"{lt['model']['median_lead_days_when_warned']:.0f} days",
                 f"{lt['model']['median_lead_days_when_warned'] - lt['rule']['median_lead_days_when_warned']:+.0f} vs rule")
        h.metric("Onsets checked", f"{lt['model']['onsets']:,}")
    if by_year is not None:
        st.subheader("PR-AUC in each test year")
        st.bar_chart(by_year.assign(year=by_year.year.astype(str)).set_index("year")[["rule_pr_auc", "model_pr_auc"]]
                     .rename(columns={"rule_pr_auc": "Persistence rule", "model_pr_auc": "Model"}), stack=False)
    if by_region is not None:
        with st.expander(f"PR-AUC in each region ({int(by_region.model_better.sum())} of {len(by_region)} won by the model)"):
            st.dataframe(by_region.sort_values("rows", ascending=False).round(3), width="stretch", hide_index=True)
    if fi is not None:
        st.subheader("What the model relies on (feature importance)")
        st.bar_chart(fi.head(12).set_index("feature"), horizontal=True, sort="-importance")
    if rules is not None:
        st.subheader("Association rules (FP-Growth)")
        st.dataframe(rules.head(20), width="stretch", hide_index=True)
