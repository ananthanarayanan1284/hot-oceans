"""Leakage audit: does any model input change when the future is removed?

For random cell-days t, the features are computed twice: from the cell's full series, and from the series cut off at
day t (as an operational system would see it: the Hobday detection is re-run on the cut series with the same fixed
climatology and threshold). Any difference means the feature used information from after t.
The label is excluded (it describes the future by design). Neighbour features are built from the same-day values of
`ratio`, `exceed` and `confirmed`, so they inherit the result for those three columns.

    python experiments/leakage_audit.py [n_cells] [days_per_cell]   (default 40 cells x 60 days, sample box)"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import hot_oceans  # noqa: F401,E402
from hot_oceans import config, hobday  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import pyarrow.dataset as ds  # noqa: E402

from pipeline.features import CELL_FEATURES, cell_features  # noqa: E402

CHECK = CELL_FEATURES + ["exceed", "confirmed"]


def main(n_cells=40, per_cell=60, seed=1):
    cfg = config.load("pc", "dev")
    rng = np.random.default_rng(seed)
    dset = ds.dataset(str(cfg.data("lake", "sst_anom")), format="parquet", partitioning="hive")
    frags = list(dset.get_fragments())
    rows = []
    for frag in rng.choice(frags, size=min(n_cells, len(frags)), replace=False):
        t = frag.to_table(columns=["cell_id", "date", "sst", "clim", "thresh", "ratio", "category"]).to_pandas()
        cid = rng.choice(t.cell_id.unique())
        s = t[t.cell_id == cid].sort_values("date").reset_index(drop=True)
        dates = pd.DatetimeIndex(pd.to_datetime(s.date))
        seas, thr = np.full(366, np.nan), np.full(366, np.nan)      # the fixed climatology curves (by day of year)
        seas[hobday.doy366(dates) - 1], thr[hobday.doy366(dates) - 1] = s.clim, s.thresh
        full = cell_features(s)
        # days after the first leap year so the day-of-year climatology curves are complete in the cut series
        for i in rng.choice(np.arange(1200, len(s) - 10), size=per_cell, replace=False):
            c = s.iloc[:i + 1].copy()
            c["category"] = hobday.detect(dates[:i + 1], c.sst.to_numpy(), seas, thr)["category"].to_numpy()
            cut = cell_features(c)
            a, b = full.iloc[i], cut.iloc[i]
            for col in CHECK:
                x, y = float(a[col]), float(b[col])
                same = (np.isnan(x) and np.isnan(y)) or abs(x - y) <= 1e-5 * max(1.0, abs(x))
                rows.append({"cell_id": cid, "date": a["date"], "feature": col, "same": same, "full": x, "cut": y})
    res = pd.DataFrame(rows)
    summary = res.groupby("feature").same.agg(checked="size", mismatches=lambda v: int((~v).sum()))
    print(f"checked {res[['cell_id', 'date']].drop_duplicates().shape[0]:,} cell-days x {len(CHECK)} inputs")
    print(summary.to_string())
    bad = res[~res.same]
    if len(bad):
        print("\nexamples of mismatches:\n", bad.head(10).to_string(index=False))
    return summary


if __name__ == "__main__":
    args = [int(a) for a in sys.argv[1:3]]
    main(*args)
