"""Title-slide map for the presentation: heatwave days per cell in 2024, drawn on the deck's navy background.

    python presentation/make_hero_map.py      (reads outputs/full/dashboard; writes presentation/assets/hero_2024.png)
"""
from pathlib import Path

import numpy as np
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
DASH = ROOT / "outputs" / "full" / "dashboard"
OUT = ROOT / "presentation" / "assets"
BG = (0x0B, 0x25, 0x45)          # slide background (land is drawn in this colour, so it disappears)
SCALE = 6                         # pixels per 0.25° cell

cells = pd.read_parquet(DASH / "cells.parquet", columns=["cell_id", "lat", "lon"])
daily = pd.read_parquet(DASH / "daily_cat.parquet", columns=["cell_id", "date"])
daily = daily[pd.to_datetime(daily.date).dt.year == 2024]
days = daily.groupby("cell_id").size()
cells["days"] = cells.cell_id.map(days).fillna(0).to_numpy()

rows, cols = 240, 360            # 30°S–30°N, 30°E–120°E at 0.25°
r = ((29.875 - cells.lat) / 0.25).round().astype(int)
c = ((cells.lon - 30.125) / 0.25).round().astype(int)
grid = np.full((rows, cols), np.nan)
grid[r, c] = cells.days

cmap = LinearSegmentedColormap.from_list("heat", ["#17426E", "#6B3F6E", "#C4473A", "#F08A3C", "#FFD98A"])
rgba = (cmap(np.clip(np.nan_to_num(grid) / 300, 0, 1))[:, :, :3] * 255).astype(np.uint8)
rgba[np.isnan(grid)] = BG
img = Image.fromarray(rgba).resize((cols * SCALE, rows * SCALE), Image.NEAREST)
OUT.mkdir(parents=True, exist_ok=True)
img.save(OUT / "hero_2024.png", optimize=True)
print(OUT / "hero_2024.png", img.size, f"mean days {cells.days.mean():.1f}")
