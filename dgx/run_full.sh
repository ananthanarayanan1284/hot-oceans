#!/usr/bin/env bash
# Full Indian Ocean run on the DGX, stage by stage. Every stage is resumable, so re-running
# this script continues where it stopped. Start it so it survives logging out:
#   nohup bash dgx/run_full.sh > logs/run_full.log 2>&1 &
# Pass stage names to run only some of them:  bash dgx/run_full.sh stage_c_events stage_d_regimes_rules
set -uo pipefail
cd "$(dirname "$0")/.."
CONDA_BASE="$(conda info --base 2>/dev/null || echo "$HOME/miniforge3")"
source "$CONDA_BASE/etc/profile.d/conda.sh"
conda activate hot-oceans
mkdir -p logs

STAGES=("$@")
[ ${#STAGES[@]} -eq 0 ] && STAGES=(download_aux download_oisst stage_a_ingest stage_b_detect stage_c_events
                                   stage_d_regimes_rules stage_e_model stage_f_case_study export_dashboard)
for s in "${STAGES[@]}"; do
  echo "[$(date '+%F %T')] START $s"
  if python -u -m "pipeline.$s" --env dgx --mode full > "logs/${s}_full.log" 2>&1; then
    echo "[$(date '+%F %T')] DONE  $s"
  else
    echo "[$(date '+%F %T')] FAILED $s  (see logs/${s}_full.log); stopping"
    exit 1
  fi
done
echo "[$(date '+%F %T')] ALL STAGES DONE"
