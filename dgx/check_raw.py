"""Count valid SST values per day in each raw OISST file and list days that differ from the usual ocean count
(a sign of a corrupted or unmasked download). Run on the DGX: python dgx/check_raw.py data/full/raw/oisst
Exit code 1 if any day differs. With --delete-bad, files holding odd days are removed so the
downloader fetches them again."""
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import xarray as xr

files = sorted(Path(sys.argv[1]).glob("oisst_*.nc"))
per_day = {}
for f in files:
    with xr.open_dataset(f) as ds:
        v = ds["sst"].values
        ok = np.isfinite(v) & (v >= -2) & (v <= 40)
        n = ok.reshape(v.shape[0], -1).sum(axis=1)
        b = (np.isfinite(v) & ~ok).reshape(v.shape[0], -1).sum(axis=1)
        for t, k, bb in zip(ds["time"].values, n, b):
            per_day[str(t)[:10]] = (int(k), int(bb))
usual = Counter(k for k, _ in per_day.values()).most_common(1)[0][0]
odd = {d: kb for d, kb in per_day.items() if kb[0] != usual or kb[1]}
print(f"files: {len(files)}  days: {len(per_day)}  usual ocean values a day: {usual}  odd days: {len(odd)}")
by_month = Counter(d[:7] for d in odd)
print("odd days by month:", dict(sorted(by_month.items())))
for d, (k, b) in sorted(odd.items()):
    if by_month[d[:7]] < 5:   # isolated days (whole bad months are listed above)
        print(f"  isolated: {d}  valid {k}  out-of-range {b}")
bad_years = sorted({d[:4] for d in odd})
print("bad years:", " ".join(bad_years) or "none")
if "--delete-bad" in sys.argv:
    for y in bad_years:
        (Path(sys.argv[1]) / f"oisst_{y}.nc").unlink()
    print(f"deleted {len(bad_years)} files")
sys.exit(1 if odd else 0)
