#!/usr/bin/env bash
# One-time setup on the DGX: Miniforge (only if no conda), the hot-oceans environment, smoke test.
# Run from the project folder:  bash dgx/setup_dgx.sh
set -euo pipefail
cd "$(dirname "$0")/.."

if ! command -v conda >/dev/null 2>&1 && [ ! -x "$HOME/miniforge3/bin/conda" ]; then
  echo "[setup] installing Miniforge into $HOME/miniforge3"
  curl -fsSL -o /tmp/miniforge.sh https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-Linux-x86_64.sh
  bash /tmp/miniforge.sh -b -p "$HOME/miniforge3"
  rm -f /tmp/miniforge.sh
fi
CONDA_BASE="$(conda info --base 2>/dev/null || echo "$HOME/miniforge3")"
source "$CONDA_BASE/etc/profile.d/conda.sh"

if conda env list | grep -q '^hot-oceans '; then
  echo "[setup] environment hot-oceans already exists"
else
  echo "[setup] creating environment hot-oceans (takes several minutes)"
  conda env create -f environment.yml
fi
conda activate hot-oceans
java -version 2>&1 | head -1
python -c "import pyspark, sedona, geopandas, xarray; print('pyspark', pyspark.__version__, '| sedona', sedona.version)"

echo "[setup] unit tests"
python -m pytest tests -q
echo "[setup] Spark + Sedona smoke test"
python -m pipeline.smoke_test --env dgx --mode full
echo "[setup] done"
