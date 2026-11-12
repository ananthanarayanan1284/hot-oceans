#!/usr/bin/env bash
# Report what this machine offers for the Hot Oceans full run. Read-only: changes nothing.
echo "== host";      hostname; whoami; uname -sr
echo "== cpu";       nproc; lscpu 2>/dev/null | grep -E 'Model name|Socket|Core\(s\)' | sed 's/  */ /g'
echo "== memory";    free -g | head -2
echo "== disk (home)"; df -h "$HOME" | tail -1
for d in /scratch /raid /data "/scratch/$USER" "/raid/$USER"; do
  [ -d "$d" ] && { echo "== disk ($d)"; df -h "$d" | tail -1; [ -w "$d" ] && echo "   writable" || echo "   not writable"; }
done
echo "== gpu";       (nvidia-smi -L 2>/dev/null || echo "no nvidia-smi")
echo "== conda";     (command -v conda || ls -d "$HOME/miniforge3" 2>/dev/null || echo "no conda")
echo "== java";      (java -version 2>&1 | head -1 || echo "no java")
echo "== scheduler"; (command -v sbatch && sinfo -s 2>/dev/null | head -5) || echo "no SLURM"
echo "== internet";  for u in https://psl.noaa.gov https://conda.anaconda.org https://repo1.maven.org; do
  printf '%s -> ' "$u"; curl -s -o /dev/null -m 15 -w '%{http_code}\n' "$u" || echo failed; done
echo "== python";    (python3 --version 2>&1)
