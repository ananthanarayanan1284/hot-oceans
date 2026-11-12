"""Hot Oceans: marine heatwave detection, tracking and prediction for the Indian Ocean."""
import os
import sys
from pathlib import Path

# On Windows a system-wide PROJ_LIB (e.g. from a PostgreSQL/PostGIS install) can point pyproj at an
# incompatible proj.db. Prefer the active conda environment's own PROJ and GDAL data.
if os.name == "nt":
    # MKL 2025's threaded layer fails to load on this Windows setup (crash 0xC06D007F in any BLAS call).
    # Spark already parallelises the work, so single-threaded MKL costs nothing here.
    os.environ.setdefault("MKL_THREADING_LAYER", "SEQUENTIAL")

_share = Path(sys.prefix) / "Library" / "share"
if os.name == "nt" and (_share / "proj" / "proj.db").exists():
    os.environ["PROJ_LIB"] = os.environ["PROJ_DATA"] = str(_share / "proj")
    if (_share / "gdal").exists():
        os.environ["GDAL_DATA"] = str(_share / "gdal")
