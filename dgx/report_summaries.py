"""Small per-cell, per-year summaries for the report maps (run on the DGX after Stage B):
    python dgx/report_summaries.py   ->  outputs/full/report/cell_year.parquet
Columns: cell_id, year, mhw_days, strong_days (category >= 2), mean_anom (annual mean SST anomaly)."""
from pathlib import Path

import pandas as pd
import pyarrow.dataset as ds

root = Path(__file__).resolve().parents[1]
lake = root / "data" / "full" / "lake" / "sst_anom"
out = root / "outputs" / "full" / "report"
out.mkdir(parents=True, exist_ok=True)
parts = []
for b in sorted(lake.glob("cell_bucket=*")):
    t = ds.dataset(str(b), format="parquet").to_table(columns=["cell_id", "year", "category", "anomaly"]).to_pandas()
    t["hot"] = t.category > 0
    t["strong"] = t.category >= 2
    parts.append(t.groupby(["cell_id", "year"]).agg(mhw_days=("hot", "sum"), strong_days=("strong", "sum"),
                                                    mean_anom=("anomaly", "mean")).reset_index())
    print(b.name, len(parts[-1]), flush=True)
res = pd.concat(parts, ignore_index=True)
res.astype({"cell_id": "int32", "year": "int16", "mhw_days": "int16", "strong_days": "int16",
            "mean_anom": "float32"}).to_parquet(out / "cell_year.parquet", index=False)
print("rows", len(res), "cells", res.cell_id.nunique(), "years", res.year.nunique())
