#!/usr/bin/env bash
# Download OISST years in 4 parallel, non-overlapping ranges, then run the whole pipeline.
# The pipeline's own download step afterwards fills any year that failed (it skips finished years).
#   setsid nohup bash dgx/parallel_download_then_run.sh > logs/parallel.log 2>&1 < /dev/null &
set -uo pipefail
cd "$(dirname "$0")/.."
CONDA_BASE="$(conda info --base 2>/dev/null || echo "$HOME/miniforge3")"
source "$CONDA_BASE/etc/profile.d/conda.sh"
conda activate hot-oceans
mkdir -p logs

RANGES=("1982 1992" "1993 2003" "2004 2014" "2015 2025")
pids=()
for r in "${RANGES[@]}"; do
  set -- $r
  echo "[$(date '+%F %T')] download $1-$2"
  python -u -m pipeline.download_oisst --env dgx --mode full --years "$1" "$2" > "logs/download_${1}_${2}.log" 2>&1 &
  pids+=($!)
done
for p in "${pids[@]}"; do wait "$p"; done
echo "[$(date '+%F %T')] parallel downloads finished: $(ls data/full/raw/oisst/*.nc 2>/dev/null | wc -l) files"
bash dgx/run_full.sh download_oisst stage_a_ingest stage_b_detect stage_c_events stage_d_regimes_rules \
                     stage_e_model stage_f_case_study export_dashboard
