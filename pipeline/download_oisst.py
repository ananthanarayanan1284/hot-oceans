"""Download daily OISST v2.1 SST for the configured box, one NetCDF per year.

Default source: NOAA PSL THREDDS (OPeNDAP). Only the box is transferred, requested one month at a
time so each request stays small. Alternative: --source erddap (NOAA CoastWatch ERDDAP).
Resumable: finished years are skipped; a year is written to .part first and renamed when complete.
On the DGX run this on the login node if compute nodes have no internet.
"""
import time
from urllib.parse import quote

import numpy as np
import requests
import xarray as xr

from hot_oceans import cli, runlog


def retry(fn, what: str, tries: int = 5):
    for attempt in range(1, tries + 1):
        try:
            return fn()
        except Exception as e:  # network / DAP errors
            if attempt == tries:
                raise RuntimeError(f"giving up on {what}: {e}") from e
            wait = 20 * attempt
            print(f"  {what}: attempt {attempt} failed ({e}); retrying in {wait}s")
            time.sleep(wait)


def valid_per_day(da):
    """(ocean values per day, count of impossible values). The land mask never changes, so every day
    of a clean download has the same count and no values outside -2..40 °C."""
    v = da.values
    ok = np.isfinite(v) & (v >= -2) & (v <= 40)
    return ok.reshape(v.shape[0], -1).sum(axis=1), int((np.isfinite(v) & ~ok).sum())


def fetch_psl(cfg, year: int, dest, tries: int = 5):
    box = cfg.box
    url = cfg["sources"]["oisst_psl"].format(year=year)

    def load_month(ds, m):
        idx = np.where(ds["time"].dt.month.values == m)[0]
        sel = dict(time=slice(int(idx[0]), int(idx[-1]) + 1))
        return retry(lambda: ds["sst"].isel(**sel)
                     .sel(lat=slice(box["lat_min"], box["lat_max"]), lon=slice(box["lon_min"], box["lon_max"]))
                     .load(), f"{year}-{m:02d}")

    ds = retry(lambda: xr.open_dataset(url), f"open {year}")
    parts = {m: load_month(ds, m) for m in np.unique(ds["time"].dt.month.values)}
    # A dropped OPeNDAP stream can hand back a half-filled array without raising, so check every month
    # against the year's usual ocean count and fetch the odd ones again on a fresh connection.
    for attempt in range(1, tries + 1):
        stats = {m: valid_per_day(p) for m, p in parts.items()}
        usual = np.bincount(np.concatenate([n for n, _ in stats.values()])).argmax()
        bad = [m for m, (n, b) in stats.items() if b or (n != usual).any()]
        if not bad:
            break
        if attempt == tries:
            raise RuntimeError(f"{year}: months {bad} still look corrupted after {tries} tries")
        print(f"  {year}: months {bad} look corrupted (expected {usual} ocean values a day); fetching again")
        time.sleep(20 * attempt)
        ds = retry(lambda: xr.open_dataset(url), f"reopen {year}")
        parts.update({m: load_month(ds, m) for m in bad})
    out = xr.concat([parts[m] for m in sorted(parts)], dim="time").to_dataset(name="sst")
    tmp = dest.with_suffix(".nc.part")
    out.to_netcdf(tmp, encoding={"sst": {"zlib": True, "complevel": 4}})
    tmp.replace(dest)
    return out.sizes


def fetch_erddap(cfg, year: int, dest):
    box, half = cfg.box, 0.125
    q = (f"sst[({year}-01-01T12:00:00Z):1:({year}-12-31T12:00:00Z)][(0.0):1:(0.0)]"
         f"[({box['lat_min'] + half}):1:({box['lat_max'] - half})]"
         f"[({box['lon_min'] + half}):1:({box['lon_max'] - half})]")
    url = f"{cfg['sources']['oisst_erddap']}?{quote(q, safe='')}"
    tmp = dest.with_suffix(".nc.part")

    def get():
        with requests.get(url, stream=True, timeout=600) as r:
            r.raise_for_status()
            with open(tmp, "wb") as f:
                for chunk in r.iter_content(chunk_size=1 << 20):
                    f.write(chunk)
    retry(get, f"erddap {year}")
    tmp.replace(dest)
    return None


def main():
    cfg, args = cli.parse(__doc__, lambda ap: (
        ap.add_argument("--years", nargs=2, type=int, metavar=("START", "END")),
        ap.add_argument("--source", choices=["psl", "erddap"], default="psl")))
    start, end = args.years or (cfg["years"]["start"], cfg["years"]["end"])
    out = cfg.data("raw", "oisst")
    out.mkdir(parents=True, exist_ok=True)
    fetch = fetch_psl if args.source == "psl" else fetch_erddap
    for year in range(start, end + 1):
        dest = out / f"oisst_{year}.nc"
        if dest.exists() and not args.force:
            continue
        print(f"[download] {year} from {args.source}")
        with runlog.timed(cfg, "download", f"oisst_{year}", dest) as rec:
            sizes = fetch(cfg, year, dest)
            if sizes:
                rec["rows"] = int(np.prod(list(sizes.values())))
                rec["note"] = str(dict(sizes))


if __name__ == "__main__":
    main()
