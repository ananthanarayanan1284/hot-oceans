#!/bin/bash
# Usage: sbatch slurm/run_stage.sbatch stage_b_detect        (adjust resources to the DGX's rules)
#SBATCH --job-name=hot-oceans
#SBATCH --cpus-per-task=32
#SBATCH --mem=180G
#SBATCH --time=08:00:00
#SBATCH --output=logs/%x-%j.out
# Some DGX queues only grant CPUs with a GPU request; uncomment if so (Spark will not use it).
##SBATCH --gres=gpu:1

set -euo pipefail
STAGE=${1:?give a pipeline module, e.g. stage_b_detect}
shift
source ~/miniforge3/etc/profile.d/conda.sh
conda activate hot-oceans
cd "${SLURM_SUBMIT_DIR}"
mkdir -p logs
python -m "pipeline.${STAGE}" --env dgx --mode full "$@"
