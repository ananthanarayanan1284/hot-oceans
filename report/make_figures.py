"""Figures for the final report, made from the result files on the PC (outputs/full, outputs/dev, data/dev).
Run:  python report/make_figures.py      ->  report/figures/fig_XX_*.png  (200 dpi, 6.3 in wide)"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import hot_oceans  # noqa: F401,E402  (Windows MKL/PROJ fixes before numpy)
from hot_oceans import grid  # noqa: E402

import json  # noqa: E402

import geopandas as gpd  # noqa: E402
import matplotlib  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import pyarrow.dataset as ds  # noqa: E402
from shapely import wkt  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.colors import BoundaryNorm, ListedColormap  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Patch, Rectangle  # noqa: E402

FULL, DEV = ROOT / "outputs" / "full", ROOT / "outputs" / "dev"
OUT = ROOT / "report" / "figures"
OUT.mkdir(parents=True, exist_ok=True)

# Palette (reference data-viz palette, light mode) and Hobday category colours (same as the dashboard).
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
INK, INK2, MUTED, GRIDC, AXIS = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"
LAND, OCEAN = "#dedbd2", "#f3f6fa"
CAT = {1: "#E38A1E", 2: "#CF531C", 3: "#A3231B", 4: "#5E1214"}
CAT_NAME = {1: "Moderate", 2: "Strong", 3: "Severe", 4: "Extreme"}
HEAT = ListedColormap(["#fdeee4", "#fbd5bd", "#f7b48e", "#f08f5f", "#e26a37", "#c64f1f", "#9c3a14", "#6e280d"])
W = 6.3

plt.rcParams.update({
    "font.family": ["Segoe UI", "Arial", "DejaVu Sans"], "font.size": 8.5, "axes.titlesize": 9,
    "axes.titleweight": "bold", "axes.titlelocation": "left", "axes.edgecolor": AXIS, "axes.labelcolor": INK2,
    "axes.linewidth": 0.8, "xtick.color": INK2, "ytick.color": INK2, "xtick.labelsize": 7.5, "ytick.labelsize": 7.5,
    "axes.spines.top": False, "axes.spines.right": False, "axes.grid": False, "grid.color": GRIDC,
    "grid.linewidth": 0.6, "legend.frameon": False, "legend.fontsize": 7.5, "savefig.dpi": 200,
    "figure.facecolor": "white", "axes.facecolor": "white"})

# 0.25° box grid: global row/col of the box's south-west cell.
BOX = dict(lat_min=-30, lat_max=30, lon_min=30, lon_max=120)
R0, C0 = int((BOX["lat_min"] + 90) / 0.25), int(BOX["lon_min"] / 0.25)
NR, NC = int((BOX["lat_max"] - BOX["lat_min"]) / 0.25), int((BOX["lon_max"] - BOX["lon_min"]) / 0.25)
EXTENT = [BOX["lon_min"], BOX["lon_max"], BOX["lat_min"], BOX["lat_max"]]

cells = pd.read_parquet(FULL / "dashboard" / "cells.parquet")


def to_grid(cell_ids, values, fill=np.nan):
    g = np.full((NR, NC), fill, dtype=float)
    r, c = grid.row_col(np.asarray(cell_ids))
    ok = (r - R0 >= 0) & (r - R0 < NR) & (c - C0 >= 0) & (c - C0 < NC)
    g[r[ok] - R0, c[ok] - C0] = np.asarray(values, dtype=float)[ok]
    return g


OCEAN_MASK = ~np.isnan(to_grid(cells.cell_id, np.ones(len(cells))))


def base_map(ax, extent=EXTENT, coast=True, ticks=10):
    land = np.where(OCEAN_MASK, np.nan, 1.0)
    ax.imshow(np.where(OCEAN_MASK, 1.0, np.nan), extent=EXTENT, origin="lower", cmap=ListedColormap([OCEAN]),
              interpolation="nearest", zorder=0)
    ax.imshow(land, extent=EXTENT, origin="lower", cmap=ListedColormap([LAND]), interpolation="nearest", zorder=3)
    if coast:
        lon = np.linspace(BOX["lon_min"] + 0.125, BOX["lon_max"] - 0.125, NC)
        lat = np.linspace(BOX["lat_min"] + 0.125, BOX["lat_max"] - 0.125, NR)
        ax.contour(lon, lat, OCEAN_MASK.astype(float), levels=[0.5], colors="#8d8a80", linewidths=0.35, zorder=4)
    ax.set_xlim(extent[0], extent[1]); ax.set_ylim(extent[2], extent[3]); ax.set_aspect("equal")
    xt = np.arange(np.ceil(extent[0] / ticks) * ticks, extent[1] + 0.1, ticks)
    yt = np.arange(np.ceil(extent[2] / ticks) * ticks, extent[3] + 0.1, ticks)
    ax.set_xticks(xt); ax.set_yticks(yt)
    ax.set_xticklabels([f"{x:.0f}°E" for x in xt])
    ax.set_yticklabels([f"{abs(y):.0f}°{'N' if y > 0 else ('S' if y < 0 else '')}" for y in yt])
    for s in ("top", "right"):
        ax.spines[s].set_visible(True)


def save(fig, name):
    fig.patches.append(Rectangle((0.002, 0.002), 0.996, 0.996, transform=fig.transFigure, fill=False,
                                 edgecolor="#5a5a5a", linewidth=0.8))
    fig.savefig(OUT / name, bbox_inches=None)
    plt.close(fig)
    print("saved", name)


def fig01_study_area():
    meow = gpd.read_file(ROOT / "data" / "aux" / "meow" / "meow.geojson").cx[30:120, -30:30]
    fig, ax = plt.subplots(figsize=(W, 4.45))
    fig.subplots_adjust(left=0.08, right=0.98, top=0.93, bottom=0.08)
    base_map(ax)
    meow.boundary.plot(ax=ax, color=AQUA, linewidth=0.45, zorder=2)
    kw = dict(color=INK2, linewidth=0.9, linestyle=(0, (4, 3)), zorder=5)
    ax.plot([30, 120], [5, 5], **kw); ax.plot([30, 120], [-5, -5], **kw)
    ax.plot([78, 78], [5, 30], **kw); ax.plot([100, 100], [5, 30], **kw); ax.plot([80, 80], [-30, -5], **kw)
    lab = dict(fontsize=8, fontweight="bold", color=INK, ha="center", zorder=6,
               bbox=dict(boxstyle="round,pad=0.25", fc="white", ec="none", alpha=0.85))
    for x, y, t in ((63, 12, "Arabian Sea"), (89, 12.5, "Bay of\nBengal"), (110, 8, "Andaman /\nS. China Sea edge"),
                    (52, -1, "Equatorial"), (55, -20, "South-west"), (100, -20, "South-east")):
        ax.text(x, y, t, **lab)
    ax.add_patch(Rectangle((65, 5), 15, 10, fill=False, edgecolor=ORANGE, linewidth=1.6, zorder=6))
    ax.text(65.4, 15.6, "Sample (dev) box", color=ORANGE, fontsize=7.5, fontweight="bold", zorder=6)
    ax.plot(72.64, 10.57, marker="*", markersize=11, color=BLUE, markeredgecolor="white", zorder=7)
    ax.annotate("Lakshadweep\ncase study", (72.64, 10.57), (55.5, 6.2), fontsize=7.5, color=BLUE, zorder=7,
                arrowprops=dict(arrowstyle="-", color=BLUE, lw=0.8))
    ax.set_title("Indian Ocean study box (30°S–30°N, 30°E–120°E): 58,334 ocean cells at 0.25°")
    ax.legend(handles=[Patch(fc=OCEAN, ec=AXIS, label="Ocean cell (analysed)"), Patch(fc=LAND, ec=AXIS, label="Land (masked)"),
                       plt.Line2D([], [], color=AQUA, lw=1, label="MEOW ecoregion boundary"),
                       plt.Line2D([], [], color=INK2, lw=1, ls=(0, (4, 3)), label="Analysis sector boundary")],
              loc="lower left", fontsize=7, framealpha=0.9, frameon=True, edgecolor="none")
    save(fig, "fig01_study_area.png")


def box(ax, x, y, w, h, title, lines=(), fc="#ffffff", ec=AXIS, tc=INK, bold=True, size=7.6):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.004,rounding_size=0.012", fc=fc, ec=ec, lw=0.9))
    ax.text(x + w / 2, y + h - 0.022, title, ha="center", va="top", fontsize=size, color=tc,
            fontweight="bold" if bold else "normal")
    for i, line in enumerate(lines):
        ax.text(x + w / 2, y + h - 0.052 - i * 0.026, line, ha="center", va="top", fontsize=6.6, color=INK2)


def arrow(ax, a, b, color=MUTED):
    ax.add_patch(FancyArrowPatch(a, b, arrowstyle="-|>", mutation_scale=9, color=color, lw=1.0))


def fig02_architecture():
    fig = plt.figure(figsize=(W, 4.9))
    ax = fig.add_axes([0, 0, 1, 1]); ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off")
    ax.text(0.5, 0.965, "Hot Oceans system architecture", ha="center", fontsize=9.5, fontweight="bold", color=INK)
    # Sources
    ax.text(0.115, 0.905, "DATA SOURCES", ha="center", fontsize=7, color=MUTED, fontweight="bold")
    src = [("NOAA OISST v2.1", ["0.25° daily SST", "1982–2025, 44 NetCDF"]), ("MEOW ecoregions", ["232 polygons", "GeoJSON"]),
           ("DMI (IOD index)", ["monthly, NOAA PSL"]), ("ONI (ENSO index)", ["monthly, NOAA CPC"])]
    for i, (t, l) in enumerate(src):
        box(ax, 0.02, 0.76 - i * 0.165, 0.19, 0.125, t, l)
    # DGX
    ax.add_patch(FancyBboxPatch((0.255, 0.13), 0.45, 0.77, boxstyle="round,pad=0.004,rounding_size=0.015",
                                fc="#f2f7fd", ec=BLUE, lw=1.0))
    ax.text(0.48, 0.875, "NVIDIA DGX  ·  Spark 3.5 local[48] + Apache Sedona 1.6 + MLlib",
            ha="center", fontsize=7.4, color=BLUE, fontweight="bold")
    stages = [("A  Ingest & clean", "NetCDF → Parquet lake (937 M rows), MEOW join (ST_Contains)"),
              ("B  Detect", "Hobday climatology, 90th-pct threshold, categories"),
              ("C  Events", "grid DBSCAN → footprints (ST_ConvexHull) → ST_Intersects links"),
              ("D  Regimes & rules", "K-Means (k by silhouette) · FP-Growth"),
              ("E  Onset model", "neighbour features · Random Forest / GBT · spatial CV"),
              ("F  Case study", "Lakshadweep 2023–24, out of sample"),
              ("G  Export", "small Parquet / GeoJSON files (~110 MB)")]
    for i, (t, l) in enumerate(stages):
        y = 0.765 - i * 0.1
        box(ax, 0.275, y, 0.41, 0.082, t, [l], fc="white", ec="#b9d2f0", size=7.4)
        if i:
            arrow(ax, (0.48, y + 0.1), (0.48, y + 0.083), BLUE)
    # source -> stage that reads it (A: OISST, MEOW; D and E: DMI/ONI phases and features)
    for (sy, ty) in ((0.8225, 0.815), (0.6575, 0.79), (0.4925, 0.53), (0.3275, 0.43)):
        arrow(ax, (0.212, sy), (0.274, ty), MUTED)
    ax.text(0.115, 0.205, "DMI and ONI feed stage D\n(phases) and stage E (features)", ha="center", fontsize=6.4,
            color=INK2, style="italic")
    # PC
    ax.add_patch(FancyBboxPatch((0.745, 0.13), 0.235, 0.77, boxstyle="round,pad=0.004,rounding_size=0.015",
                                fc="#fdf3ee", ec=ORANGE, lw=1.0))
    ax.text(0.8625, 0.875, "Windows PC", ha="center", fontsize=7.4, color=ORANGE, fontweight="bold")
    pc = [("Dev run", ["sample box, all years", "debug every stage"]), ("PostGIS 3.4", ["events, footprints,", "cells + GiST index"]),
          ("Streamlit + pydeck", ["6-tab dashboard", "localhost:8501"]), ("Report & figures", ["matplotlib, Word"])]
    for i, (t, l) in enumerate(pc):
        box(ax, 0.762, 0.7 - i * 0.175, 0.2, 0.13, t, l)
    arrow(ax, (0.686, 0.206), (0.744, 0.206), ORANGE)
    ax.text(0.715, 0.225, "copy\nresults", ha="center", va="bottom", fontsize=6.2, color=ORANGE)
    ax.text(0.5, 0.06, "Control path: PC → JupyterHub REST API (dgx/jhub.py: run · upload · download)",
            ha="center", fontsize=6.8, color=INK2, style="italic")
    save(fig, "fig02_architecture.png")


def fig03_detection():
    cs = pd.read_parquet(FULL / "dashboard" / "case_study.parquet")
    cs["date"] = pd.to_datetime(cs.date)
    fig, ax = plt.subplots(figsize=(W, 3.3))
    fig.subplots_adjust(left=0.09, right=0.98, top=0.9, bottom=0.27)
    for c in (1, 2):
        m = (cs.category == c).to_numpy()
        ax.fill_between(cs.date, cs.thresh, cs.sst, where=m & (cs.sst > cs.thresh).to_numpy(), color=CAT[c],
                        step="mid", linewidth=0, label=f"Heatwave: {CAT_NAME[c]}", zorder=2)
    ax.plot(cs.date, cs.sst, color=INK, lw=1.2, label="SST (OISST)", zorder=3)
    ax.plot(cs.date, cs.thresh, color=BLUE, lw=1.1, ls=(0, (4, 2)), label="90th-percentile threshold", zorder=3)
    ax.plot(cs.date, cs.clim, color=MUTED, lw=1.1, label="Climatology (1991–2020)", zorder=3)
    ax.axvline(pd.Timestamp("2023-05-12"), color=INK2, lw=0.7, ls=":")
    lo = cs[["sst", "clim", "thresh"]].min().min() - 0.2
    ax.text(pd.Timestamp("2023-05-15"), lo + 0.1, "onset 12 May 2023", fontsize=7, color=INK2)
    ax.set_ylabel("Sea surface temperature (°C)")
    ax.yaxis.grid(True); ax.set_axisbelow(True)
    ax.xaxis.set_major_formatter(matplotlib.dates.DateFormatter("%b %Y"))
    ax.set_title("Hobday detection at the Lakshadweep cell (10.6°N, 72.6°E), May 2023 – June 2024")
    ax.legend(ncol=3, loc="upper center", bbox_to_anchor=(0.5, -0.1), fontsize=7)
    ax.set_ylim(lo, cs.sst.max() + 0.3)
    save(fig, "fig03_detection.png")


def fig04_runtime():
    log = pd.read_csv(FULL / "tables" / "run_log.csv")
    log = log[(log.timestamp >= "2026-11-04T11:35") & (log.env == "dgx")]
    e = log[log.stage == "E"]
    rows = [("A  Ingest + clean + MEOW join", log[log.stage == "A"].seconds.sum(), "937.5 M rows"),
            ("B  Hobday detection (64 buckets)", log[log.stage == "B"].seconds.sum(), "937.5 M rows"),
            ("C  DBSCAN + footprints + linking", log[log.stage == "C"].seconds.sum(), "66.5 M hot cell-days"),
            ("D  K-Means + FP-Growth", log[log.stage == "D"].seconds.sum(), "14,472 events"),
            ("E1 Neighbour features", e[e.step == "neighbour_features"].seconds.sum(), "937.5 M rows"),
            ("E2 Training table (64 buckets)", e[e.step.str.startswith("features_bucket")].seconds.sum(), "124 M rows kept"),
            ("E3 Random Forest (5-fold CV + fit)", e[e.step == "train_random_forest"].seconds.sum(), "3.0 M training rows"),
            ("E4 GBT (5-fold CV + fit)", e[e.step == "train_gbt"].seconds.sum(), "3.0 M training rows"),
            ("F  Case study", log[log.stage == "F"].seconds.sum(), "427 days"),
            ("G  Export for dashboard", log[log.stage == "G"].seconds.sum(), "14 M rows")]
    df = pd.DataFrame(rows, columns=["step", "sec", "note"])
    df["min"] = df.sec / 60
    fig, ax = plt.subplots(figsize=(W, 3.4))
    fig.subplots_adjust(left=0.36, right=0.97, top=0.88, bottom=0.12)
    y = np.arange(len(df))[::-1]
    ax.barh(y, df["min"], color=BLUE, height=0.62)
    for yi, m, n in zip(y, df["min"], df.note):
        ax.text(m + 0.6, yi, f"{m:.1f} min · {n}", va="center", fontsize=7, color=INK2)
    ax.set_yticks(y); ax.set_yticklabels(df.step, fontsize=7.4, color=INK)
    ax.set_xlabel("Wall-clock minutes on the DGX (Spark local[48], 200 GB driver)")
    ax.set_xlim(0, df["min"].max() * 1.45)
    ax.xaxis.grid(True); ax.set_axisbelow(True)
    ax.set_title(f"Full-basin run time by step (total {df['min'].sum():.0f} min)")
    save(fig, "fig04_runtime.png")
    return df


def fig05_trend():
    y = pd.read_parquet(FULL / "dashboard" / "mhw_days_per_year.parquet")
    fig, ax = plt.subplots(figsize=(W, 2.9))
    fig.subplots_adjust(left=0.09, right=0.98, top=0.86, bottom=0.13)
    ax.bar(y.year, y.mean_mhw_days, color=BLUE, width=0.72, label="Mean heatwave days per ocean cell")
    k, b = np.polyfit(y.year, y.mean_mhw_days, 1)
    ax.plot(y.year, k * y.year + b, color=ORANGE, lw=1.6, ls=(0, (5, 2)), label=f"Linear trend: +{k * 10:.1f} days per decade")
    for yr in (1998, 2016, 2024):
        v = float(y.loc[y.year == yr, "mean_mhw_days"].iloc[0])
        ax.text(yr, v + 3, f"{yr}\n{v:.0f} d", ha="center", fontsize=6.8, color=INK)
    ax.set_ylabel("Days per year"); ax.set_xlim(1981.2, 2025.8); ax.set_ylim(0, 160)
    ax.yaxis.grid(True); ax.set_axisbelow(True)
    ax.legend(loc="upper left")
    ax.set_title("Marine heatwave days per year, Indian Ocean box mean (1982–2025)")
    save(fig, "fig05_trend.png")


def fig06_days_2023_2024():
    d = pd.read_parquet(FULL / "dashboard" / "daily_cat.parquet", columns=["cell_id", "date"])
    d["year"] = pd.to_datetime(d.date).dt.year
    per = d.groupby(["cell_id", "year"]).size().unstack(fill_value=0).reindex(cells.cell_id, fill_value=0)
    fig, axs = plt.subplots(1, 2, figsize=(W, 3.0))
    fig.subplots_adjust(left=0.07, right=0.99, top=0.9, bottom=0.3, wspace=0.12)
    norm = BoundaryNorm([0, 25, 50, 100, 150, 200, 250, 300, 366], HEAT.N)
    for ax, yr in zip(axs, (2023, 2024)):
        base_map(ax, ticks=20)
        g = to_grid(per.index, per[yr].to_numpy())
        im = ax.imshow(np.ma.masked_invalid(g), extent=EXTENT, origin="lower", cmap=HEAT, norm=norm,
                       interpolation="nearest", zorder=1)
        ax.set_title(f"{yr}: mean {per[yr].mean():.0f} days per cell", fontsize=8.3)
        ax.tick_params(labelsize=6.5)
    cax = fig.add_axes([0.25, 0.15, 0.5, 0.04])
    cb = fig.colorbar(im, cax=cax, orientation="horizontal")
    cb.set_label("Marine heatwave days in the year", fontsize=7.5, color=INK2); cb.ax.tick_params(labelsize=6.8)
    cb.outline.set_edgecolor(AXIS)
    save(fig, "fig06_days_2023_2024.png")


def fig07_snapshot(day="2024-02-06"):
    d = pd.read_parquet(FULL / "dashboard" / "daily_cat.parquet")
    d = d[pd.to_datetime(d.date) == day]
    share = cells.set_index("cell_id").area_km2.reindex(d.cell_id).sum() / cells.area_km2.sum()
    fig, ax = plt.subplots(figsize=(W, 4.4))
    fig.subplots_adjust(left=0.08, right=0.98, top=0.93, bottom=0.08)
    base_map(ax)
    cmap = ListedColormap([CAT[c] for c in (1, 2, 3, 4)])
    g = to_grid(d.cell_id, d.category)
    ax.imshow(np.ma.masked_invalid(g), extent=EXTENT, origin="lower", cmap=cmap,
              norm=BoundaryNorm([0.5, 1.5, 2.5, 3.5, 4.5], 4), interpolation="nearest", zorder=1)
    counts = d.category.value_counts()
    ax.legend(handles=[Patch(fc=CAT[c], label=f"{CAT_NAME[c]} ({counts.get(c, 0):,} cells)") for c in (1, 2, 3, 4)],
              loc="lower left", fontsize=7, frameon=True, framealpha=0.92, edgecolor="none", title="Category (Hobday 2018)",
              title_fontsize=7)
    t = pd.Timestamp(day)
    ax.set_title(f"Heatwave categories on {t.day} {t:%B %Y}: {len(d):,} cells, {share:.1%} of the ocean area")
    save(fig, "fig07_snapshot_2024-02-06.png")
    return len(d), share


def fig08_dev_change():
    t = ds.dataset(str(ROOT / "data" / "dev" / "lake" / "sst_anom"), format="parquet", partitioning="hive") \
          .to_table(columns=["cell_id", "year", "category"]).to_pandas()
    t["hot"] = t.category > 0
    py = t.groupby(["cell_id", "year"]).hot.sum().reset_index()
    a = py[py.year.between(1982, 1991)].groupby("cell_id").hot.mean()
    b = py[py.year.between(2016, 2025)].groupby("cell_id").hot.mean()
    ext = [65, 80, 5, 15]
    fig, axs = plt.subplots(1, 2, figsize=(W, 2.9))
    fig.subplots_adjust(left=0.07, right=0.99, top=0.9, bottom=0.32, wspace=0.14)
    norm = BoundaryNorm([0, 10, 20, 40, 60, 80, 100, 120, 160], HEAT.N)
    for ax, s, title in zip(axs, (a, b), ("1982–1991", "2016–2025")):
        base_map(ax, extent=ext, ticks=5)
        im = ax.imshow(np.ma.masked_invalid(to_grid(s.index, s.to_numpy())), extent=EXTENT, origin="lower",
                       cmap=HEAT, norm=norm, interpolation="nearest", zorder=1)
        ax.plot(72.64, 10.57, marker="*", markersize=9, color=BLUE, markeredgecolor="white", zorder=7)
        ax.set_title(f"{title}: mean {s.mean():.0f} days per year", fontsize=8.3)
        ax.tick_params(labelsize=6.5)
    cax = fig.add_axes([0.25, 0.16, 0.5, 0.045])
    cb = fig.colorbar(im, cax=cax, orientation="horizontal")
    cb.set_label("Mean marine heatwave days per year (sample box, ★ Lakshadweep)", fontsize=7.3, color=INK2)
    cb.ax.tick_params(labelsize=6.8); cb.outline.set_edgecolor(AXIS)
    save(fig, "fig08_dev_change.png")
    return a.mean(), b.mean(), len(a)


def fig09_events():
    ev = pd.read_parquet(FULL / "postgis" / "mhw_events.parquet")
    ev["year"] = pd.to_datetime(ev.start).dt.year
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(W, 2.7), gridspec_kw={"width_ratios": [1.35, 1]})
    fig.subplots_adjust(left=0.08, right=0.98, top=0.85, bottom=0.17, wspace=0.28)
    n = ev.groupby("year").size()
    a1.bar(n.index, n.values, color=BLUE, width=0.72)
    a1.set_title("Events starting per year"); a1.set_ylabel("Events"); a1.yaxis.grid(True); a1.set_axisbelow(True)
    bins = np.logspace(np.log10(5), np.log10(1100), 26)
    a2.hist(ev.duration_days, bins=bins, color=BLUE, edgecolor="white", linewidth=0.6)
    a2.set_xscale("log"); a2.set_yscale("log")
    a2.set_xticks([5, 10, 30, 100, 300, 1000]); a2.set_xticklabels(["5", "10", "30", "100", "300", "1000"])
    a2.set_title("Duration of events"); a2.set_xlabel("Duration (days, log scale)"); a2.set_ylabel("Events (log)")
    a2.axvline(ev.duration_days.median(), color=ORANGE, lw=1.2, ls=(0, (4, 2)))
    a2.text(ev.duration_days.median() * 1.12, a2.get_ylim()[1] * 0.5, f"median {ev.duration_days.median():.0f} d",
            color=ORANGE, fontsize=7)
    save(fig, "fig09_events.png")


def pick_moving_event(ev):
    """A 30–60-day event whose daily centroid moves far but smoothly (a clean tracking example)."""
    best, best_disp = None, 0.0
    for _, r in ev[ev.duration_days.between(30, 60)].iterrows():
        if not r.track_wkt:
            continue
        tr = np.array(wkt.loads(r.track_wkt).coords)
        step = np.hypot(*np.diff(tr, axis=0).T)
        disp = float(np.hypot(*(tr[-1] - tr[0])))
        if step.max() < 1.5 and disp > best_disp:
            best, best_disp = r, disp
    return best, best_disp


def fig10_event_track():
    ev = gpd.read_file(FULL / "dashboard" / "events.geojson")
    row, disp = pick_moving_event(ev)
    fp = gpd.read_parquet(FULL / "postgis" / "mhw_footprints.parquet")
    fp["date"] = pd.to_datetime(fp.date)
    g = fp.groupby("event").agg(start=("date", "min"), end=("date", "max"), n=("date", "nunique"))
    idx = g[(g.start == pd.Timestamp(row.start)) & (g.end == pd.Timestamp(row.end)) & (g.n == row.duration_days)].index[0]
    days = fp[fp.event == idx].sort_values("date")
    day_no = (days.date - days.date.min()).dt.days.to_numpy()
    x0, y0, x1, y1 = days.total_bounds
    pad = 3
    ext = [max(30, x0 - pad), min(120, x1 + pad), max(-30, y0 - pad), min(30, y1 + pad)]
    fig, ax = plt.subplots(figsize=(W, 4.0))
    fig.subplots_adjust(left=0.09, right=0.88, top=0.92, bottom=0.09)
    base_map(ax, extent=ext, ticks=5)
    ramp = ListedColormap(["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"])
    norm = plt.Normalize(0, day_no.max())
    for (_, d), k in zip(days.iterrows(), day_no):
        if k % 3 == 0 or k == day_no.max():
            gpd.GeoSeries([d.geometry]).boundary.plot(ax=ax, color=ramp(norm(k)), linewidth=0.9, zorder=2)
    tr = np.array(wkt.loads(row.track_wkt).coords)
    ax.plot(tr[:, 0], tr[:, 1], color=ORANGE, lw=1.6, zorder=5)
    ax.plot(*tr[0], marker="o", ms=7, color=ORANGE, mec="white", zorder=6)
    ax.plot(*tr[-1], marker="s", ms=7, color=INK, mec="white", zorder=6)
    sm = plt.cm.ScalarMappable(cmap=ramp, norm=norm)
    cax = fig.add_axes([0.9, 0.15, 0.022, 0.7])
    cb = fig.colorbar(sm, cax=cax); cb.set_label("Day of the event", fontsize=7.5, color=INK2)
    cb.ax.tick_params(labelsize=6.8); cb.outline.set_edgecolor(AXIS)
    s, e = pd.Timestamp(row.start), pd.Timestamp(row.end)
    ax.legend(handles=[plt.Line2D([], [], color="#3987e5", lw=1, label="Daily footprint (every 3rd day)"),
                       plt.Line2D([], [], color=ORANGE, lw=1.6, label="Centroid track"),
                       plt.Line2D([], [], color=ORANGE, marker="o", lw=0, label=f"Start {s:%d %b %Y}"),
                       plt.Line2D([], [], color=INK, marker="s", lw=0, label=f"End {e:%d %b %Y}")],
              loc="best", fontsize=7, frameon=True, framealpha=0.92, edgecolor="none")
    ax.set_title(f"Tracking event {row.event_id}: {int(row.duration_days)} days, peak {row.peak_area_km2 / 1e3:,.0f} thousand km², "
                 f"moved {disp:.1f}°", fontsize=8.6)
    save(fig, "fig10_event_track.png")
    return row.event_id, s.date(), e.date(), int(row.duration_days), row.peak_area_km2, row.max_intensity, \
        int(row.max_category), disp, len(days)


def fig11_regimes():
    sel = pd.read_csv(FULL / "tables" / "kmeans_selection.csv")
    iod = pd.read_csv(FULL / "tables" / "regime_by_iod_phase.csv").set_index("iod_phase").loc[["IOD-", "IOD0", "IOD+"]]
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(W, 2.7), gridspec_kw={"width_ratios": [1, 1.25]})
    fig.subplots_adjust(left=0.09, right=0.98, top=0.85, bottom=0.17, wspace=0.3)
    a1.plot(sel.k, sel.silhouette, color=BLUE, lw=2, marker="o", ms=5)
    best = sel.loc[sel.silhouette.idxmax()]
    a1.plot(best.k, best.silhouette, marker="o", ms=9, mfc="none", mec=ORANGE, mew=1.6)
    a1.text(best.k + 0.3, best.silhouette - 0.003, f"chosen: k = {int(best.k)} ({best.silhouette:.3f})", color=ORANGE, fontsize=7)
    a1.set_xlabel("Number of clusters k"); a1.set_ylabel("Silhouette score"); a1.set_title("Choosing k")
    a1.yaxis.grid(True); a1.set_axisbelow(True)
    names = {"0": "Regime 0: short, intense", "1": "Regime 1: long, large", "2": "Regime 2: short, mild"}
    x = np.arange(len(iod)); w = 0.26
    for i, (col, c) in enumerate(zip(["0", "1", "2"], (BLUE, ORANGE, AQUA))):
        a2.bar(x + (i - 1) * w, iod[col], width=w - 0.03, color=c, label=names[col])
    a2.set_xticks(x); a2.set_xticklabels(["IOD negative", "IOD neutral", "IOD positive"])
    a2.set_ylabel("Share of events"); a2.set_ylim(0, 0.85); a2.yaxis.grid(True); a2.set_axisbelow(True)
    a2.set_title("Regime mix by Indian Ocean Dipole phase"); a2.legend(fontsize=6.6, loc="upper left")
    save(fig, "fig11_regimes.png")


def fig12_model():
    m = json.loads((FULL / "tables" / "model_metrics.json").read_text())
    fi = pd.read_csv(FULL / "tables" / "feature_importance.csv").head(10)[::-1]
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(W, 2.9), gridspec_kw={"width_ratios": [1, 1.15]})
    fig.subplots_adjust(left=0.09, right=0.98, top=0.85, bottom=0.2, wspace=0.55)
    names = ["Random\nguess", "Persistence\nrule", "Random\nForest", "GBT\n(chosen)"]
    vals = [m["test_positive_rate"], m["persistence_baseline"]["pr_auc_test"], m["random_forest"]["pr_auc_test"],
            m["gbt"]["pr_auc_test"]]
    a1.bar(names, vals, color=[AXIS, MUTED, BLUE, BLUE], width=0.62)
    for i, v in enumerate(vals):
        a1.text(i, v + 0.012, f"{v:.3f}", ha="center", fontsize=7.2, color=INK)
    a1.set_ylabel("PR-AUC, test years 2019–2025"); a1.set_ylim(0, 0.75); a1.yaxis.grid(True); a1.set_axisbelow(True)
    a1.set_title(f"Test skill ({m['test_rows'] / 1e6:.0f} M cell-days)"); a1.tick_params(axis="x", labelsize=6.8)
    labels = {"nb_ratio_7": "Neighbour heat, 7×7 box", "nb_ratio": "Neighbour heat, 8 cells",
              "nb_ratio_21": "Neighbour heat, 21×21 box", "nb_ratio_max_7": "Hottest neighbour, 7×7",
              "days_since_exceed": "Days since above threshold", "nb_exceed_21": "Share above thr., 21×21",
              "ratio_30": "Own heat, 30-day mean", "trend_1": "1-day anomaly change",
              "exceed_days_30": "Days above thr., last 30", "ratio_7": "Own heat, 7-day mean",
              "run_len": "Days above thr. in a row", "ratio": "Own heat today"}
    fi = fi.assign(label=[labels.get(f, f) for f in fi.feature])
    a2.barh(fi.label, fi.importance, color=BLUE, height=0.65)
    for yv, v in enumerate(fi.importance):
        a2.text(v + 0.004, yv, f"{v:.3f}", va="center", fontsize=6.6, color=INK2)
    a2.set_xlim(0, 0.31); a2.set_title(f"{m['best_model'].upper()} feature importance (top 10)")
    a2.tick_params(axis="y", labelsize=6.8)
    a2.xaxis.grid(True); a2.set_axisbelow(True)
    save(fig, "fig12_model.png")


def fig13_case_warning():
    cs = pd.read_parquet(FULL / "dashboard" / "case_study.parquet")
    cs["date"] = pd.to_datetime(cs.date)
    s = json.loads((FULL / "tables" / "case_study_summary.json").read_text())
    cs = cs[(cs.date >= "2023-04-28") & (cs.date <= "2023-05-20")]
    thr, onset, warn = s["threshold"], pd.Timestamp(s["first_heatwave_day"]), pd.Timestamp(s["first_warning_day"])
    fig, ax = plt.subplots(figsize=(W, 2.7))
    fig.subplots_adjust(left=0.09, right=0.98, top=0.86, bottom=0.14)
    hot = cs.category > 0
    ax.fill_between(cs.date, 0, 1, where=hot.to_numpy(), color=CAT[1], alpha=0.18, step="mid", linewidth=0,
                    label="Heatwave days")
    ax.plot(cs.date, cs.p_onset, color=BLUE, lw=1.6, marker="o", ms=3, label="Model risk: heatwave within 7 days")
    ax.axhline(thr, color=INK2, lw=0.9, ls=(0, (4, 2)), label=f"Warning threshold {thr:.2f} (chosen on 2015–2018)")
    ax.axvline(warn, color=BLUE, lw=0.8, ls=":"); ax.axvline(onset, color=ORANGE, lw=1.0)
    ax.text(warn - pd.Timedelta(days=0.3), 0.5, f"first warning\n{warn:%d %b}", ha="right", fontsize=7, color=BLUE)
    ax.text(onset + pd.Timedelta(days=0.8), 0.06, f"heatwave begins {onset:%d %b}\nlead time {s['lead_days']} days",
            fontsize=7, color=ORANGE)
    ax.set_ylim(0, 1); ax.set_ylabel("Risk score"); ax.yaxis.grid(True); ax.set_axisbelow(True)
    ax.xaxis.set_major_formatter(matplotlib.dates.DateFormatter("%d %b"))
    ax.legend(loc="upper left", fontsize=6.8, frameon=True, framealpha=0.92, edgecolor="none")
    ax.set_title(f"Lakshadweep 2023: early warning from the {s['model'].upper()} model (never saw 2019–2025)")
    save(fig, "fig13_case_warning.png")


def fig15_trust():
    y = pd.read_csv(FULL / "tables" / "trust_by_year.csv")
    cal = pd.read_csv(FULL / "tables" / "trust_calibration.csv")
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(W, 2.8), gridspec_kw={"width_ratios": [1.35, 1]})
    fig.subplots_adjust(left=0.08, right=0.98, top=0.86, bottom=0.17, wspace=0.3)
    x = np.arange(len(y)); w = 0.38
    a1.bar(x - w / 2, y.rule_pr_auc, width=w - 0.03, color=MUTED, label="Persistence rule")
    a1.bar(x + w / 2, y.model_pr_auc, width=w - 0.03, color=BLUE, label="GBT model")
    a1.set_xticks(x); a1.set_xticklabels(y.year); a1.set_ylim(0.4, 0.75); a1.set_ylabel("PR-AUC")
    a1.yaxis.grid(True); a1.set_axisbelow(True); a1.legend(loc="upper left", ncol=2)
    a1.set_title("Model beats the rule in every test year")
    for ver, c, mk in (("raw", ORANGE, "o"), ("calibrated", BLUE, "s")):
        t = cal[cal.version == ver]
        a2.plot(t.predicted, t.observed, color=c, marker=mk, ms=3.5, lw=1.2,
                label="Raw score" if ver == "raw" else "After isotonic calibration")
    a2.plot([0, 1], [0, 1], color=AXIS, lw=0.9, ls="--", label="Perfect")
    a2.set_xlim(0, 0.75); a2.set_ylim(0, 0.75); a2.set_xlabel("Predicted risk"); a2.set_ylabel("Observed frequency")
    a2.grid(True); a2.set_axisbelow(True); a2.legend(loc="upper left", fontsize=6.6)
    a2.set_title("Calibration on the test years")
    save(fig, "fig15_trust.png")


if __name__ == "__main__":
    figs = [fig01_study_area, fig02_architecture, fig03_detection, fig04_runtime, fig05_trend, fig06_days_2023_2024,
            fig07_snapshot, fig08_dev_change, fig09_events, fig10_event_track, fig11_regimes, fig12_model,
            fig13_case_warning, fig15_trust]
    want = sys.argv[1:]   # e.g. "fig03 fig10" to remake only some figures
    for f in figs:
        if not want or any(f.__name__.startswith(w) for w in want):
            res = f()
            if res is not None:
                print(f.__name__, "->", res if not isinstance(res, pd.DataFrame) else "\n" + res.round(2).to_string(index=False))
