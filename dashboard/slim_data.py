"""Shrink the two large dashboard files so the app fits in the memory of a small cloud server.

    python dashboard/slim_data.py [--mode full]

Same rows and values; only the storage types change: dates become real dates (not text), cell ids int32,
categories int8, risk scores float32, and rows are pre-sorted by date (the app slices one day at a time).
"""
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
mode = sys.argv[sys.argv.index("--mode") + 1] if "--mode" in sys.argv else "full"
D = ROOT / "outputs" / mode / "dashboard"

TYPES = {"daily_cat.parquet": {"cell_id": "int32", "category": "int8"},
         "risk.parquet": {"cell_id": "int32", "p_onset": "float32"}}

for name, types in TYPES.items():
    p = D / name
    d = pd.read_parquet(p)
    before = d.memory_usage(deep=True).sum() / 1e6
    d = (d.assign(date=pd.to_datetime(d.date)).astype(types)
          .sort_values(["date", "cell_id"], kind="stable").reset_index(drop=True))
    d.to_parquet(p, index=False, compression="zstd")
    print(f"{name}: {len(d):,} rows, memory {before:,.0f} MB -> {d.memory_usage(deep=True).sum() / 1e6:,.0f} MB, "
          f"file {p.stat().st_size / 1e6:,.1f} MB")
