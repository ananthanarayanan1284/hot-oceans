# Hot Oceans — PC + DGX workflow

Rule of thumb: **big data and heavy jobs stay on the DGX; code, small samples, results and the dashboard live on the PC.***

---

## 1. What lives where

| Thing | DGX (server) | PC (laptop) |
|---|---|---|
| Raw OISST NetCDF (~5.5 GB) | ✅ stored here | ❌ never |
| Full GeoParquet lake (~1B rows) | ✅ | ❌ |
| Dev-box sample (lat 5–15, lon 65–80, all years, ~30M rows, ~150 MB) | ✅ created here | ✅ copied down for coding/debugging |
| Climatology, MHW flags (full) | ✅ | ❌ (only the dev-box slice) |
| Event catalogue, regimes, rules, model metrics, predictions | ✅ produced here | ✅ copied down |
| Dashboard extracts (small, see §5) | ✅ produced here | ✅ copied down |
| PostGIS (derived tables) | ✅ full version | ✅ Docker copy restored from `pg_dump` |
| Code | ✅ `git pull` | ✅ written here, `git push` |
| Streamlit dashboard | ❌ | ✅ runs here |
| Figures, `run_log.csv`, report | copy | ✅ final home |

## 2. Same code, two machines

One repo, one `config.yaml` switch:

```yaml
env: pc            # pc | dgx
paths:
  pc:  {data: ~/hot-oceans/data,          out: ~/hot-oceans/outputs}
  dgx: {data: /scratch/<user>/hot-oceans/data, out: /scratch/<user>/hot-oceans/outputs}
spark:
  pc:  {master: "local[8]",  driver_memory: "8g",   shuffle_partitions: 64}
  dgx: {master: "local[32]", driver_memory: "128g", shuffle_partitions: 512}
mode: dev          # dev = small box, full = whole Indian Ocean box
```

- Every script reads `env` and `mode`; nothing else changes between machines.
- Set `spark.local.dir` to scratch on the DGX (shuffle files can be 10–15 GB).
- Match `local[N]` and driver memory to what the scheduler gives you, not the whole node.

## 3. Moving things between PC and DGX

| What | Direction | How |
|---|---|---|
| Code | PC → DGX | `git push` on PC, `git pull` on DGX (GitHub/GitLab private repo) |
| Dev-box sample | DGX → PC | `rsync -avz dgx:/scratch/<user>/hot-oceans/data/dev/ ~/hot-oceans/data/dev/` |
| Results & dashboard extracts | DGX → PC | `rsync -avz dgx:/scratch/<user>/hot-oceans/outputs/ ~/hot-oceans/outputs/` |
| PostGIS tables | DGX → PC | `pg_dump -Fc hot_oceans > hot.dump` on DGX → rsync → `pg_restore -d hot_oceans hot.dump` into the Docker PostGIS on PC |
| OISST (if DGX compute nodes have no internet) | login node, or PC → DGX | Download on the DGX login node; last resort: download on PC and `rsync` up |

Run `rsync` from WSL Ubuntu on the PC (it has `ssh` and can install `rsync`). Set up an SSH key once and add a `dgx` entry in `~/.ssh/config` so commands stay short.

## 4. Daily loop

1. **PC:** write or fix a stage, test it on the dev-box sample (`env: pc`, `mode: dev`). Minutes per run.
2. **PC:** `git push`.
3. **DGX:** `git pull`, submit the stage as a job with `env: dgx`, `mode: full`.
4. **DGX:** job appends row counts / runtime / sizes to `outputs/tables/run_log.csv`.
5. **PC:** `rsync` outputs down, look at figures and tables, move on.

Job template (if the DGX uses SLURM; adjust to its rules):

```bash
#!/bin/bash
#SBATCH --job-name=ho-stageB
#SBATCH --cpus-per-task=32
#SBATCH --mem=160G
#SBATCH --time=08:00:00
#SBATCH --output=logs/%x-%j.out
source ~/miniforge3/etc/profile.d/conda.sh
conda activate hot-oceans
cd /scratch/$USER/hot-oceans/repo
python -m pipeline.stage_b --env dgx --mode full
```

Every stage is resumable (skips partitions already written), so a killed or timed-out job just gets resubmitted.

## 5. Dashboard extracts (made on the DGX, used on the PC)

The dashboard never reads the 1B-row lake. A final job writes small files:

| File | Content | Approx. size |
|---|---|---|
| `daily_cat_2023_2024.parquet` | Category per cell per day, 2023–24 only (uint8) | ~60 MB |
| `mhw_days_per_year.parquet` | Basin and per-cell MHW days per year | < 50 MB |
| `events.parquet` / `.geojson` | Event catalogue + tracks + peak footprints | < 50 MB |
| `regimes.parquet`, `rules.parquet` | K-Means regimes, FP-Growth rules | tiny |
| `model_metrics.json`, `feature_importance.parquet` | ML results | tiny |
| `lakshadweep_2024.parquet` | Case-study series (SST, clim, threshold, category, prediction) | tiny |

Total well under 1 GB → easy to `rsync` and fast in Streamlit on the PC.

## 6. Day-by-day split

| Day | DGX | PC |
|---|---|---|
| 1 | Get access; conda env (Python 3.11, OpenJDK 17, pinned PySpark + Sedona); download Sedona JARs on login node if compute nodes are offline; PostGIS via conda (`initdb`, `pg_ctl`); **start full OISST download**; run smoke test on a compute node | WSL + conda env (same versions); PostGIS in Docker; repo + `config.yaml`; SSH key + `dgx` alias; download MEOW, DMI, ONI (push small files to DGX) |
| 2 | Stage A full (GeoParquet lake + `cells` into PostGIS); cut dev-box sample; **Stage B full** once dev check passes | Pull dev sample; write and debug Stage B on it; hand-check one Lakshadweep cell |
| 3 | Stage C full (DBSCAN + linking → `mhw_events`) | Write/debug Stage C on dev sample; pull results; MHW-days-per-year sanity plot |
| 4 | Stage D (K-Means, FP-Growth) and Stage E (RF/GBT, temporal + spatial CV) on full data; case-study predictions; write dashboard extracts | Write/debug D and E on dev sample; pull metrics; case-study figure |
| 5 | `pg_dump`; final `rsync` of outputs; back up anything on scratch | Restore PostGIS; build Streamlit dashboard on extracts; figures; report notes |

## 7. Things to confirm with the DGX admin (Day 1)

- SSH access, scheduler (SLURM?), max job time, CPU/RAM per job (Spark needs CPUs, not GPUs).
- Is conda allowed? Docker/Singularity?
- Internet on compute nodes? On login node?
- Scratch path, quota, and how long files are kept before cleanup.
- Can a user run a PostgreSQL server process in their own job/session?

## 8. Fallbacks

- **No DGX access by end of Day 1:** run everything on the PC with the 0.5° grid.
- **PostGIS not allowed on DGX:** keep PostGIS only on the PC; load the small derived tables there from Parquet extracts.
- **No internet on DGX at all:** download OISST on the PC (~5.5 GB) and `rsync` it up once.
- **Scratch gets wiped:** keep raw downloads resumable and copy outputs to the PC at the end of each day.
