# Hot Oceans — Idea, Approach and Implementation Plan

*Prepared 17 Oct 2026. Companion to `CLAUDE.md` (the full technical spec). Target: working pipeline by 26 Oct 2026; course ends 10 Nov 2026.*

**Title:** Hot Oceans: Spatiotemporal Detection of Marine Heatwaves and Prediction of Coral Bleaching Risk across the Indian Ocean using Satellite SST Big Data, Apache Sedona and Spark MLlib

---

## 1. The idea

**The problem**
- A **marine heatwave (MHW)** is ≥5 consecutive days when sea temperature at a location stays above its seasonal 90th percentile (Hobday et al. 2016).
- MHWs cause coral bleaching. The Indian Ocean had mass bleaching in 1998, 2010, 2016, 2019–20 and 2023–24; Lakshadweep was hit badly in 2023–24.
- NOAA publishes per-pixel heat alerts, but there is no Indian Ocean catalogue of heatwave **events** (size, duration, movement) linked to what reefs experienced in field surveys. That is the gap.

**What gets built**
- **Data:** 44 years (1982–2025) of daily satellite SST (NOAA OISST, 0.25°) for the Indian Ocean box (lat −30 to 30, lon 30°E–120°E): ~60k ocean cells × ~16k days ≈ **1 billion rows**.
- **Detection:** per-cell climatology (1991–2020 baseline) and 90th-percentile threshold; every MHW day flagged with a category (Moderate / Strong / Severe / Extreme, Hobday 2018).
- **Events:** cluster each day's hot cells (DBSCAN), build footprint polygons, link footprints day to day with a Sedona spatial join → event catalogue with duration, intensity, area and track.
- **Regimes:** K-Means on event features (e.g., basin-wide long events vs short coastal bursts); relate regime frequency to El Niño (ONI) and IOD (DMI).
- **Training table:** Global Coral Bleaching Database (GCBD) surveys joined with each site's prior heat history, reef type (Allen Coral Atlas) and Coral Reef Watch heat stress.
- **ML:** Random Forest / GBT to predict bleaching severity, evaluated with spatial cross-validation; FP-Growth rules like `{DHW>8, shallow, IOD+} ⇒ Severe`.
- **Case study:** model applied to Lakshadweep 2023–24. GCBD ends in 2020, so this is a genuine out-of-sample test.
- **Dashboard:** Streamlit + pydeck: heatwave map with date slider, event explorer, reef risk layer, top rules.

**Why it satisfies the course**
- Every syllabus item has a real role: Spark + Sedona, map-reduce, cleaning, PostGIS, partitioning, clustering, classification, association rules, decision support, disaster case study (mapping table in `CLAUDE.md` §2).
- Contribution: event-level MHW analysis for the Indian Ocean + ML trained on field surveys, validated on an event the model never saw.

---

## 2. Approach

1. **Dev mode first, then full mode.** Build and test every stage on a small box, then run on the full data.
   - **Fix to the spec:** `CLAUDE.md` defines dev mode as 2023–24 only, but the climatology needs the 1991–2020 baseline, so two years cannot produce real heatwaves. Use **small box (lat 5–15, lon 65–80) × all 44 years** instead: ~30M rows, fast on any laptop, and gives real Lakshadweep results from day one.
2. **Two parallel tracks that meet at Stage E.**
   - *SST track (slow):* download → A → B → C → D. Start the full OISST download on Day 1.
   - *Survey track (small):* GCBD QC → Allen Coral Atlas sampling → Coral Reef Watch at sites. Do it while SST jobs run.
3. **Memory-safe big-data processing.**
   - Write the cell-bucketed layout year by year (append into `cell_bucket=NN/` partitions), so the 1B rows never go through one giant shuffle.
   - Run Stage B one cell bucket at a time; skip buckets already written (resumable).
   - Keep the 1B rows in GeoParquet. PostGIS stores only derived tables (cells, events, sites, training table, regions, reef cells).
4. **Simplify the risky steps.**
   - **Allen Coral Atlas:** don't vectorise 5 m reefs for the whole basin. In Google Earth Engine, export (a) geomorphic/benthic class at GCBD site points (1 km buffer, mode) and (b) reef fraction per 0.25° OISST cell. Two small CSVs cover Stages E and H.
   - **Coral Reef Watch:** the GCBD environmental CSV appears to already include thermal-stress columns — verify. If so, fetch CRW only for Indian Ocean sites and the Lakshadweep case study.
   - **DBSCAN:** cluster on grid indices (row, col), not lat/lon degrees, so eps means "1.5 cells". On a regular grid this is close to connected components with a density filter (good viva point).
   - **Event linking:** the day-to-day link table is small (~10⁵ edges) → union-find on the driver is enough; GraphFrames optional.
5. **Decision points.**
   - Indian Ocean GCBD rows < ~2,000 → train on global GCBD with an ocean-basin feature, evaluate on Indian Ocean rows.
   - Full Stage B too slow on the chosen machine → switch machines by Day 4, not later.
6. **Evidence and honesty.** Every stage logs row counts, runtime and output size to `outputs/tables/run_log.csv` (big-data evidence). Report weak model results as they are.

---

## 3. Where to run it

### Machines

| | Laptop 1 (M3 Mac) | Laptop 2 (Docker + Miniforge) | OpenSARLab (m6a.xlarge) |
|---|---|---|---|
| RAM | 8 GB | **check** | 10 GB guaranteed / 16 GB limit |
| CPU | 8 cores | **check** | 4 CPUs |
| Free disk | 94 GB | **check** | 500 GB |
| Installs | anything (no Java/Docker/Postgres yet; Python 3.9.6) | conda + Docker | conda/mamba only, no `sudo`/`apt` |
| PostGIS | Postgres.app | **Docker container** (easiest) | conda-forge `postgis` + `pg_ctl` |
| Long jobs | laptop must stay awake | laptop must stay awake | cloud, but may shut down after ~1 h idle |

### Step 0 — check Laptop 2

Run these and note the numbers:

```bash
# macOS
sysctl -n hw.memsize | awk '{print $1/1073741824 " GB RAM"}'; sysctl -n hw.ncpu; df -h ~

# Linux / WSL
free -h; nproc; df -h ~

# Any OS
conda --version
docker --version
docker info --format '{{.MemTotal}}'   # RAM given to Docker (bytes)
java -version                         # fine if missing; conda will provide Java 17
```

Windows (PowerShell): `(Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory/1GB`, `$env:NUMBER_OF_PROCESSORS`, `Get-PSDrive C`.

> **If Laptop 2 is Windows:** run Spark inside **WSL2 (Ubuntu)** with Miniforge installed inside WSL, and Docker Desktop on the WSL backend. Native-Windows PySpark needs `winutils.exe`/`hadoop.dll` to write Parquet and is a common time sink.

### Decision table

| Laptop 2 has | Plan |
|---|---|
| ≥ 16 GB RAM and ≥ 40 GB free disk | Run **everything** on Laptop 2 (full runs overnight). OpenSARLab is the backup. |
| 8–15 GB RAM | Dev mode + dashboard on Laptop 2; full runs on **OpenSARLab**. |
| < 40 GB free disk | Full runs on OpenSARLab regardless of RAM (raw ~6 GB + lake ~5 GB + Spark shuffle 2–3×). |

### Laptop 2 setup (Docker + Miniforge)

**Python / Java / Spark** — conda environment (Spark runs here, not in Docker):

```bash
mamba create -n hot-oceans -c conda-forge python=3.11 openjdk=17 -y
conda activate hot-oceans
java -version   # should print 17
```

The exact PySpark + Sedona pair gets pinned in `requirements.txt` / `environment.yml` on Day 1 after checking Sedona's compatibility table.

**PostGIS** — Docker container:

```bash
docker run -d --name hot-oceans-pg \
  -e POSTGRES_USER=hot -e POSTGRES_PASSWORD=hot -e POSTGRES_DB=hot_oceans \
  -p 5432:5432 -v hot_oceans_pgdata:/var/lib/postgresql/data \
  postgis/postgis:16-3.4

docker exec -it hot-oceans-pg psql -U hot -d hot_oceans -c "SELECT postgis_full_version();"
```

- On Apple Silicon, if Docker reports "no matching manifest", add `--platform linux/amd64`.
- Limit Docker Desktop's memory to ~2–3 GB so Spark has most of the RAM.
- Put the DSN (`postgresql://hot:hot@localhost:5432/hot_oceans`) in `config.yaml`.

### OpenSARLab notes (if used for full runs)

1. **Pick the larger profile** (m6a.xlarge). If DUK runs its own class lab, its sizes and rules may differ — check the server options at login.
2. **Stay under the 10 GB guarantee**, not the 16 GB limit: memory above the guarantee isn't promised and the job can be killed. Spark: `local[4]`, driver ~7–8 GB, ~64 shuffle partitions.
3. **Idle shutdown:** the server may stop after ~1 h of inactivity, and it's unclear whether a running script counts as activity. Keep stages resumable, and on Day 1 run a 90-minute test job with the browser tab closed to see if it survives.
4. **PostGIS without sudo:** `mamba install -c conda-forge postgresql postgis`, `initdb -D ~/pgdata`, then `pg_ctl -D ~/pgdata -l ~/pg.log start` every session.
5. **Dashboard runs on a laptop**, not OpenSARLab (opening a Streamlit port there isn't confirmed). It only reads small precomputed outputs anyway.
6. **Back up:** storage is deleted after 30 days of inactivity, and non-NASA access is month-to-month. Keep code on GitHub; copy final outputs (events, predictions, figures, `run_log.csv`, `pg_dump`) to a laptop.
7. Workflow: develop on a laptop → `git push` → `git pull` on OpenSARLab → run full mode → paste logs/row counts back.

---

## 4. Implementation plan

| Day | Date | Work | Done when |
|---|---|---|---|
| 1 | 17 Oct | Check Laptop 2 and choose machines (§3). Conda env + PostGIS up. Repo skeleton, `config.yaml` (`env: local \| osl`), pinned versions, Spark/Sedona session. Tiny test requests to every data source (D1–D6). **Start full OISST download** on the full-run machine. Start Earth Engine exports. Download GCBD, MEOW ecoregions, DMI/ONI. | Sedona starts; PostGIS responds; every source answers |
| 2 | 18 Oct | **Stage A** dev → full: NetCDF → long table → GeoParquet (by year + by cell bucket); `cells` table into PostGIS | ~1B rows logged; no NaNs or duplicate (cell_id, date) |
| 3 | 19 Oct | **Stage B** on dev box: climatology + Hobday detection + categories; hand-check one cell; launch full run overnight | 2023–24 Lakshadweep MHW days look right |
| 4 | 20 Oct | Full Stage B sanity plot (MHW days per year). Survey track: GCBD QC + EDA, count Indian Ocean rows | Peaks in 1998, 2010, 2016, 2019–20, 2023–24; global vs Indian Ocean training decided |
| 5 | 21 Oct | **Stage C**: daily DBSCAN → blob polygons → Sedona `ST_Intersects` linking → event features → `mhw_events` in PostGIS | Event catalogue + track map |
| 6 | 22 Oct | **Stage D**: K-Means (k 3–8, elbow + silhouette), regimes vs DMI/ONI. **Stage E**: joins → `training_table` | Class balance logged |
| 7 | 23 Oct | **Stage F**: RF multiclass + GBT binary, class weights, spatial vs random CV, feature importance. **Stage G**: FP-Growth | Macro-F1, per-class recall, top rules by lift |
| 8 | 24 Oct | **Stage H**: reef heat exposure by region/year; Lakshadweep 2023–24 out-of-sample prediction vs CMFRI reports | Case-study figure |
| 9 | 25 Oct | **Stage I**: Streamlit + pydeck dashboard on precomputed outputs | Loads in seconds |
| 10 | 26 Oct | All figures, `run_log.csv` summary, report notes per stage, limitations | Deliverables checklist (`CLAUDE.md` §10) ticked |
| — | 27 Oct – 5 Nov | Buffer; report + slides; viva prep. Stretch (Sedona vs PostGIS join benchmark) only if ahead | — |

---

## 5. Proposed changes to `CLAUDE.md` (not yet applied)

- Dev mode = small box × **all years** (not 2023–24 only).
- Add `env: local | osl` to `config.yaml`; PostGIS via Docker on Laptop 2, conda-forge on OpenSARLab.
- Allen Coral Atlas: point sampling + reef fraction per OISST cell in GEE, instead of vectorising the whole box.
- Coral Reef Watch: optional enrichment if GCBD's thermal-stress columns are sufficient; required for the Lakshadweep case study.
- Stage A writes the cell-bucketed layout year by year; Stage B processes one bucket at a time.

## 6. Open questions

1. Laptop 2: OS, RAM, CPU cores, free disk (run Step 0).
2. OpenSARLab: which server profiles appear at login (public lab or a DUK class lab)?
3. Apply the §5 changes to `CLAUDE.md`?

---

### Sources (OpenSARLab)
- [OpenSARLab user guide — profiles, storage, lifecycle, no sudo](https://opensarlab-docs.asf.alaska.edu/user-guides/opensarlab)
- [OpenScienceLab environment and account lifecycle](https://opensarlab-docs.asf.alaska.edu/user-guides/OpenSARLab_environment)
- [Installing software (mamba, no apt)](https://opensarlab-docs.asf.alaska.edu/software)
- [Conda environments](https://opensarlab-docs.asf.alaska.edu/conda-environments)
- [Logging out and server shutdown](https://opensarlab-docs.asf.alaska.edu/logging-out-and-server-shutdown)
