"""Small per-event footprint file for the dashboard's Events tab (runs on the PC, no Spark).

Reads   outputs/<mode>/postgis/mhw_footprints.parquet   (all daily footprints, written by Stage C)
        outputs/<mode>/dashboard/events.geojson          (event catalogue)
Writes  outputs/<mode>/dashboard/event_footprints.parquet  (event_id, date, area, category, simplified WKB)

  python -m pipeline.export_event_footprints --mode full
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hot_oceans.config import load  # noqa: E402  (first: Windows env fixes)

import geopandas as gpd  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import shapely  # noqa: E402
from shapely import wkt  # noqa: E402


def main():
    mode = sys.argv[sys.argv.index("--mode") + 1] if "--mode" in sys.argv else "full"
    cfg = load(env="pc", mode=mode)
    fp = gpd.read_parquet(cfg.out("postgis", "mhw_footprints.parquet"))
    fp["date"] = pd.to_datetime(fp.date)
    ev = gpd.read_file(cfg.out("dashboard", "events.geojson"))

    # Stage C numbers events internally (fp.event); the catalogue only keeps event_id. Match them by
    # start, end, number of days and the first point of the centroid track (same daily means as Stage C).
    g = fp.groupby("event").agg(start=("date", "min"), end=("date", "max"), n=("date", "nunique"))
    first = fp[fp.date == fp.event.map(g.start)].groupby("event").agg(lon=("clon", "mean"), lat=("clat", "mean"))
    g = g.join(first)
    g["key"] = list(zip(g.start, g.end, g.n, g.lon.round(3), g.lat.round(3)))

    def ev_key(r):
        x, y = wkt.loads(r.track_wkt).coords[0] if r.track_wkt else (np.nan, np.nan)
        return (pd.Timestamp(r.start), pd.Timestamp(r.end), int(r.duration_days), round(x, 3), round(y, 3))

    lookup = {k: e for e, k in g.key.items()}
    ev_map = {}
    for _, r in ev.iterrows():
        e = lookup.get(ev_key(r))
        if e is not None:
            ev_map[e] = r.event_id
    print(f"matched {len(ev_map)} of {len(ev)} events")

    out = fp[fp.event.isin(ev_map)].copy()
    out["event_id"] = out.event.map(ev_map)
    geom = shapely.set_precision(shapely.simplify(out.geometry.values, 0.02), 0.001)
    out = pd.DataFrame({"event_id": out.event_id.values, "date": out.date.dt.date.values,
                        "area_km2": out.area_km2.round(0).values, "max_cat": out.max_cat.values,
                        "wkb": shapely.to_wkb(geom)})
    path = cfg.out("dashboard", "event_footprints.parquet")
    out.sort_values(["event_id", "date"]).to_parquet(path, index=False, compression="zstd")
    print(f"saved {len(out):,} footprints to {path} ({path.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
