"""0.25° OISST grid helpers. Cell ids index the global grid, so dev and full runs share ids."""
import numpy as np

RES = 0.25
NCOL = 1440  # 360 / 0.25


def cell_id(lat, lon, res=RES):
    row = np.floor((np.asarray(lat) + 90) / res).astype(np.int64)
    col = np.floor((np.asarray(lon) % 360) / res).astype(np.int64)
    return (row * NCOL + col).astype(np.int32)


def row_col(cid):
    cid = np.asarray(cid)
    return cid // NCOL, cid % NCOL


def center(cid, res=RES):
    row, col = row_col(cid)
    lat = -90 + (row + 0.5) * res
    lon = (col + 0.5) * res
    return lat, np.where(lon > 180, lon - 360, lon)


def bucket(cid, n_buckets):
    """Spread cells evenly over buckets so Stage B can run one bucket at a time."""
    return (np.asarray(cid) % n_buckets).astype(np.int16)


def cell_area_km2(lat, res=RES):
    return (res * 111.32) ** 2 * np.cos(np.radians(lat))
