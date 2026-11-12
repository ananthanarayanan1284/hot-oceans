#!/usr/bin/env bash
# Re-fetch corrupted raw years, verify every file, then rebuild the full lake and all results from scratch.
#   setsid nohup bash dgx/redo_full.sh > logs/redo.log 2>&1 < /dev/null &
set -uo pipefail
cd "$(dirname "$0")/.."
CONDA_BASE="$(conda info --base 2>/dev/null || echo "$HOME/miniforge3")"
source "$CONDA_BASE/etc/profile.d/conda.sh"
conda activate hot-oceans
mkdir -p logs
RAW=data/full/raw/oisst

echo "[$(date '+%F %T')] checking raw files"
python dgx/check_raw.py "$RAW" --delete-bad
echo "[$(date '+%F %T')] downloading missing years (one at a time)"
python -u -m pipeline.download_oisst --env dgx --mode full > logs/download_redo.log 2>&1 || { echo "download FAILED"; exit 1; }
if ! python dgx/check_raw.py "$RAW"; then echo "raw files still not clean; stopping"; exit 1; fi

echo "[$(date '+%F %T')] removing the old lake (built from the corrupted files)"
rm -rf data/full/lake data/full/tmp data/spark-tmp
bash dgx/run_full.sh stage_a_ingest stage_b_detect stage_c_events stage_d_regimes_rules \
                     stage_e_model stage_f_case_study export_dashboard
