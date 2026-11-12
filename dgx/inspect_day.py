"""Print the out-of-range SST values for one day straight from PSL OPeNDAP (no file written).
Run: python dgx/inspect_day.py 1985-01-01"""
import sys

import numpy as np
import xarray as xr

from hot_oceans import config

cfg = config.load("dgx", "full")
day = sys.argv[1]
box = cfg.box
url = cfg["sources"]["oisst_psl"].format(year=day[:4])
for attempt in range(2):
    with xr.open_dataset(url) as ds:
        da = ds["sst"].sel(time=day).sel(lat=slice(box["lat_min"], box["lat_max"]),
                                         lon=slice(box["lon_min"], box["lon_max"])).load()
    v = da.values
    bad = np.isfinite(v) & ((v < -2) | (v > 40))
    print(f"try {attempt + 1}: valid {int((np.isfinite(v) & ~bad).sum())}  out-of-range {int(bad.sum())}")
    for i, j in zip(*np.where(bad)):
        print(f"   lat {float(da.lat[i]):7.3f} lon {float(da.lon[j]):7.3f}  sst {v[i, j]:.3f}")
