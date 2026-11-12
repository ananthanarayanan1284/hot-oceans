"""Architecture diagram of the Hot Oceans system (stand-alone, no data needed).
Run:  python report/make_architecture.py  ->  report/figures/fig02_architecture_v2.png (+ .svg)"""
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Ellipse, FancyArrowPatch, FancyBboxPatch, Rectangle  # noqa: E402

OUT = Path(__file__).resolve().parent / "figures"
OUT.mkdir(parents=True, exist_ok=True)

BLUE, BLUE_L, BLUE_E = "#2a78d6", "#f2f7fd", "#b9d2f0"
ORANGE, ORANGE_L, ORANGE_E = "#eb6834", "#fdf3ee", "#f3c3ad"
INK, INK2, MUTED, AXIS = "#0b0b0b", "#52514e", "#898781", "#c3c2b7"
GREY_L = "#f7f7f5"

plt.rcParams.update({"font.family": ["Segoe UI", "Arial", "DejaVu Sans"], "savefig.dpi": 300})

fig = plt.figure(figsize=(6.3, 4.8 * 0.885))
ax = fig.add_axes([0, 0, 1, 1])
ax.set_xlim(0, 1); ax.set_ylim(0.115, 1); ax.axis("off")


def panel(x, y, w, h, fc, ec, lw=1.0, ls="-"):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.003,rounding_size=0.014",
                                fc=fc, ec=ec, lw=lw, ls=ls))


def card(x, top, w, h, title, lines=(), ec=AXIS, ls="-", tsize=7.0, lsize=6.1):
    panel(x, top - h, w, h, "white", ec, 0.9, ls)
    ax.text(x + w / 2, top - 0.02, title, ha="center", va="top", fontsize=tsize, color=INK, fontweight="bold")
    for i, line in enumerate(lines):
        ax.text(x + w / 2, top - 0.047 - i * 0.024, line, ha="center", va="top", fontsize=lsize, color=INK2)


def arrow(a, b, color=MUTED, lw=1.0, style="-|>", ls="-", conn="arc3"):
    ax.add_patch(FancyArrowPatch(a, b, arrowstyle=style, mutation_scale=8, color=color, lw=lw,
                                 linestyle=ls, connectionstyle=conn, shrinkA=0, shrinkB=0))


# ---------------------------------------------------------------- title
ax.text(0.5, 0.968, "Hot Oceans: system architecture", ha="center", va="center", fontsize=10.5,
        fontweight="bold", color=INK)
ax.text(0.5, 0.932, "Code is built and tested on the PC, runs at full scale on the DGX, "
        "and only the small results come back", ha="center", va="center", fontsize=6.8, color=INK2)

TOP, BOT = 0.885, 0.135

# ---------------------------------------------------------------- 1. data sources
panel(0.012, BOT, 0.178, TOP - BOT, GREY_L, AXIS)
ax.text(0.101, TOP - 0.025, "1  DATA SOURCES", ha="center", va="center", fontsize=7.2, color=INK2, fontweight="bold")
sources = [("NOAA OISST v2.1", ["0.25° daily SST", "1982–2025 · 44 NetCDF"], 0.84),
           ("MEOW ecoregions", ["232 polygons", "GeoJSON"], 0.705),
           ("DMI  (IOD index)", ["monthly, NOAA PSL"], 0.58),
           ("ONI  (ENSO index)", ["monthly, NOAA CPC"], 0.47)]
for t, l, top in sources:
    card(0.022, top, 0.158, 0.105 if len(l) == 2 else 0.082, t, l)
ax.text(0.101, 0.33, "IOD / ENSO phase is\nattached to each event\nin stage D", ha="center", va="center",
        fontsize=5.9, color=MUTED, style="italic", linespacing=1.3)

# ---------------------------------------------------------------- 2. DGX
DX, DW = 0.212, 0.536
panel(DX, BOT, DW, TOP - BOT, BLUE_L, BLUE, 1.1)
ax.text(DX + DW / 2, TOP - 0.025, "2  NVIDIA DGX  ·  Spark 3.5 local[48]  ·  Sedona 1.6  ·  MLlib",
        ha="center", va="center", fontsize=7.0, color=BLUE, fontweight="bold")

stages = [("A", "Ingest & clean", "NetCDF → Parquet · QC · MEOW join (ST_Contains)", ["937.5 M", "cell-days"]),
          ("B", "Detect heatwaves (Hobday)", "1991–2020 climatology · 90th pct · ≥ 5 days", ["7.2 % of", "cell-days hot"]),
          ("C", "Build events", "grid DBSCAN → ST_ConvexHull → ST_Intersects", ["291 k footprints", "14,472 events"]),
          ("D", "Regimes & rules", "K-Means (k by silhouette) · FP-Growth", ["3 regimes", "59 rules"]),
          ("E", "Onset model + trust checks", "23 real-time features · GBT / RF vs persistence", ["PR-AUC 0.625", "rule 0.598"]),
          ("F", "Case study", "Lakshadweep 2023–24, test years only", ["warning 5 days", "before onset"]),
          ("G", "Export", "small Parquet + GeoJSON for the dashboard", ["≈ 110 MB", "copied to PC"])]
S_TOP, S_H, S_P = 0.835, 0.068, 0.0895
SX, SW = DX + 0.014, 0.372
CX, CW = SX + SW + 0.02, DX + DW - (SX + SW + 0.02) - 0.014
centers = {}
for i, (k, t, d, chip) in enumerate(stages):
    top = S_TOP - i * S_P
    y = top - S_H
    centers[k] = y + S_H / 2
    panel(SX, y, SW, S_H, "white", BLUE_E, 0.9)
    ax.text(SX + 0.02, y + S_H / 2, k, ha="center", va="center", fontsize=6.8, color="white", fontweight="bold",
            bbox=dict(boxstyle="circle,pad=0.28", fc=BLUE, ec="none"))
    ax.text(SX + 0.042, top - 0.016, t, ha="left", va="top", fontsize=6.9, color=INK, fontweight="bold")
    ax.text(SX + 0.042, top - 0.039, d, ha="left", va="top", fontsize=5.9, color=INK2)
    # result chip
    panel(CX, y + 0.004, CW, S_H - 0.008, "#e4effb", "none")
    ax.text(CX + CW / 2, y + S_H / 2, "\n".join(chip), ha="center", va="center", fontsize=5.9, color=INK,
            linespacing=1.25)
    ax.plot([SX + SW, CX], [y + S_H / 2] * 2, color=BLUE_E, lw=0.9)
    if i:
        arrow((SX + 0.02, top + S_P - S_H), (SX + 0.02, top + 0.001), BLUE, 0.9)

# data lake (horizontal cylinder) along the bottom of the DGX panel
LX, LW, LY, LH = SX, DX + DW - SX - 0.014, 0.148, 0.068
ax.add_patch(Rectangle((LX + 0.01, LY), LW - 0.02, LH, fc="#d6e6f8", ec="none"))
ax.plot([LX + 0.01, LX + LW - 0.01], [LY, LY], color=BLUE, lw=0.9)
ax.plot([LX + 0.01, LX + LW - 0.01], [LY + LH, LY + LH], color=BLUE, lw=0.9)
ax.add_patch(Ellipse((LX + 0.01, LY + LH / 2), 0.02, LH, fc="#d6e6f8", ec=BLUE, lw=0.9))
ax.add_patch(Ellipse((LX + LW - 0.01, LY + LH / 2), 0.02, LH, fc="#eaf2fc", ec=BLUE, lw=0.9))
ax.text(LX + LW / 2, LY + LH * 0.68, "Parquet data lake (26 GB): every stage reads and writes here",
        ha="center", va="center", fontsize=6.6, color=INK, fontweight="bold")
ax.text(LX + LW / 2, LY + LH * 0.3, "partitions: year · cell_bucket (cell_id % 64)  ·  _SUCCESS marker = stage can resume",
        ha="center", va="center", fontsize=5.8, color=INK2)

# sources -> stages
for sy, stage, off in ((0.7875, "A", 0.008), (0.6525, "A", -0.012), (0.539, "D", 0.008), (0.429, "D", -0.012)):
    arrow((0.18, sy), (SX, centers[stage] + off), MUTED, 0.9)

# ---------------------------------------------------------------- 3. Windows PC
PX, PW = 0.762, 0.226
panel(PX, BOT, PW, TOP - BOT, ORANGE_L, ORANGE, 1.1)
ax.text(PX + PW / 2, TOP - 0.025, "3  WINDOWS PC", ha="center", va="center", fontsize=7.2, color=ORANGE,
        fontweight="bold")
QX, QW, QH = PX + 0.012, PW - 0.024, 0.105
card(QX, 0.835, QW, QH, "Dev run", ["same code, sample box", "1,971 cells, all years"], ec=ORANGE_E)
card(QX, 0.53, QW, QH, "Dashboard", ["Streamlit + pydeck", "6 tabs · localhost:8501"], ec=ORANGE_E)
card(QX, 0.32, QW, QH, "Serving layer", ["GeoParquet tables", "PostGIS + GiST (optional)"], ec=ORANGE_E, ls=(0, (3, 2)))
mx = QX + QW / 2
arrow((mx, 0.32), (mx, 0.53 - QH), ORANGE, 0.9)             # serving -> dashboard
# divider between development and results
ax.plot([QX, QX + QW], [0.69, 0.69], color=ORANGE_E, lw=0.8, ls=(0, (2, 2)))

# G -> PC results
arrow((CX + CW, centers["G"]), (QX, 0.32 - QH / 2), ORANGE, 1.4)

fig.patches.append(Rectangle((0.002, 0.002), 0.996, 0.996, transform=fig.transFigure, fill=False,
                             edgecolor="#5a5a5a", linewidth=0.8))
for ext in ("png", "svg"):
    fig.savefig(OUT / f"fig02_architecture_v2.{ext}")
print("saved", OUT / "fig02_architecture_v2.png")
