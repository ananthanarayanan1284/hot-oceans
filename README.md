# Hot Oceans

Spatiotemporal detection, tracking and prediction of marine heatwaves across the Indian Ocean, using 44 years of daily satellite sea temperatures (NOAA OISST v2.1, 0.25°), Apache Sedona, PostGIS and Spark MLlib.

Course project, Spatial Big Data (Digital University Kerala) · Ananthanarayanan B (253318) · Supervisor: Manoj Kumar

- **Report:** [report/Hot_Oceans_Report_253318_v2.pdf](report/Hot_Oceans_Report_253318_v2.pdf)
- **Presentation:** [presentation/Hot_Oceans_Presentation_253318.pdf](presentation/Hot_Oceans_Presentation_253318.pdf) ([.pptx](presentation/Hot_Oceans_Presentation_253318.pptx))
- **Live dashboard:** https://hot-oceans.streamlit.app (or run locally with `streamlit run dashboard/app.py`)
- **Study notes:** [LESSONS.md](LESSONS.md)

Plans: [IMPLEMENTATION_PLAN_5DAY.md](IMPLEMENTATION_PLAN_5DAY.md) · PC/DGX split: [WORKFLOW_PC_DGX.md](WORKFLOW_PC_DGX.md)

## Architecture

```
NOAA OISST (PSL OPeNDAP) ─┐   MEOW ecoregions ─┐   DMI / ONI ─┐
                     ▼                    ▼              ▼
A  ingest     NetCDF → long table → Parquet lake (by year → by cell bucket) + cells (GeoParquet, Sedona join) → PostGIS
B  detect     per-cell climatology + 90th pct threshold + Hobday rule (applyInPandas, one bucket at a time)
C  events     daily DBSCAN on grid cells → footprints (Sedona) → ST_Intersects day-to-day links → union-find → catalogue → PostGIS
D  regimes    K-Means on event features (+ IOD/ENSO phase) · FP-Growth rules
E  model      onset within 7 days: Random Forest / GBT on past-only and neighbour-cell features,
              temporal holdout + spatial CV, persistence baseline
F  case study Lakshadweep 2023–24 out of sample
G  dashboard  export small files (DGX) → copy to PC → PostGIS + Streamlit/pydeck (PC)
```

| Folder | Contents |
|---|---|
| `hot_oceans/` | Library: config, Spark/Sedona session, grid helpers, Hobday detection, clustering/linking, climate indices, PostGIS writer, run log |
| `pipeline/` | One module per stage, run with `python -m pipeline.<module>` |
| `dashboard/app.py` | Streamlit + pydeck app (reads `outputs/<mode>/dashboard/`) |
| `sql/schema.sql` | PostGIS indexes and example spatial queries |
| `dgx/` | DGX helpers: `jhub.py` (run commands, upload, download through the JupyterHub API), run scripts, raw-data check |
| `slurm/run_stage.sbatch` | Job template for clusters with SLURM (the course DGX has none) |
| `tests/` | Unit tests for the heatwave core and neighbour features |
| `report/` | Final report: `make_figures.py` (figures from outputs/), `screenshot_dashboard.py`, `build_short_report.js` (Word file, npm `docx`; output `Hot_Oceans_Report_253318_v2.docx/.pdf`), `finalize_report.ps1` (Word fills contents and page numbers, exports PDF) |
| `data/`, `outputs/` | Created by the pipeline and git-ignored (5 GB of raw data), except the full-basin result tables `outputs/full/tables/` and the dashboard files `outputs/full/dashboard/` |

## Setup

**PC (Windows, Miniforge)**: the `hot-oceans` env (Python 3.11, PySpark 3.5, Sedona 1.6.1), `winutils.exe` under
`spark.pc.hadoop_home`, and PostgreSQL 13 + PostGIS 3.4 programs. `hot_oceans/__init__.py` fixes the Windows
MKL and PROJ settings, so every script imports `hot_oceans` before numpy.

```powershell
python -m pytest tests
# private project database (data\pgdata, port 5433, localhost only):
powershell -ExecutionPolicy Bypass -File sql\pg_local.ps1 init     # once; later: start | stop | status | psql
```

**Dashboard only** (no Spark needed): `pip install -r dashboard/requirements.txt`, then `streamlit run dashboard/app.py`.
It opens the full-basin files in `outputs/full/dashboard/` (use `-- --mode dev` for the small box).

**DGX (JupyterHub account, no SSH, no SLURM)**: save a JupyterHub API token in `~/.dgx_token` on the PC and the hub
address in `dgx/hub_settings.json` (`{"hub": "https://<host>:8000", "user": "<account>"}`, git-ignored), then drive
the DGX from the PC with `dgx/jhub.py`:

```powershell
python dgx/jhub.py upload pipeline/stage_e_model.py hot-oceans/pipeline/stage_e_model.py
python dgx/jhub.py run "cd ~/hot-oceans && bash dgx/setup_dgx.sh"           # Miniforge + env + tests + smoke test
python dgx/jhub.py run "cd ~/hot-oceans && setsid nohup bash dgx/parallel_download_then_run.sh > logs/parallel.log 2>&1 < /dev/null &"
python dgx/jhub.py download hot-oceans/outputs_full.tar outputs_full.tar     # after: tar -cf outputs_full.tar -C outputs full
```

## Run order

```bash
python -m pipeline.download_aux                 # DMI, ONI; put MEOW (shapefile or meow.geojson) in data/aux/meow/
python -m pipeline.download_oisst               # resumable, one file per year, every month checked
python dgx/check_raw.py data/<mode>/raw/oisst   # every day must have the same ocean count, no impossible values
python -m pipeline.stage_a_ingest
python -m pipeline.stage_b_detect               # resumable per cell bucket
python -m pipeline.stage_c_events
python -m pipeline.stage_d_regimes_rules
python -m pipeline.stage_e_model                # neighbour features, training table, RF + GBT
python -m pipeline.stage_f_case_study
python -m pipeline.export_dashboard
# on the PC, after copying outputs/full/ from the DGX:
python -m pipeline.load_postgis --env pc --mode full
streamlit run dashboard/app.py -- --mode full
```

Add `--env dgx --mode full` on the DGX (`dgx/run_full.sh` does this for a list of stages). Every stage appends row
counts, runtimes and output sizes to `outputs/<mode>/tables/run_log.csv`.

`--mode dev` runs the small box (lat 5–15, lon 65–80, all years) for fast debugging; `--mode full` runs the whole Indian Ocean box.

Do not run several OISST downloads in parallel: dropped OPeNDAP streams returned half-filled months without an error
(Januaries of 1984, 1986, 1994, 2011 and 2015 on the first full run). `download_oisst` now checks each month and
fetches odd ones again, and `dgx/redo_full.sh` re-fetches bad years and rebuilds the full lake.

## Results (final, November 2026)

- Unit tests pass on the PC and the DGX. Dev box run on the PC; full box run on the DGX (`local[48]`).
- **Data:** 937,485,714 cell-days (58,334 ocean cells × 16,071 days, 0 duplicates or nulls).
- **Trend:** mean heatwave days per cell rose from 9.6 a year (1982–91) to 60.5 (2016–25), +14.9 days per decade;
  2024 is the record (133 days). 14,472 events from 291,272 daily footprints.
- **Week-ahead warning model** (rebuilt on 8 Nov 2026 after a look-ahead leak was found and removed; audit: 0
  mismatches). Task: will a cell not yet in a confirmed heatwave be in one within 7 days? Test years 2019–25,
  32.1 M cell-days, positive rate 13.9 %:

  | | PR-AUC | PR-AUC (still below threshold) | ROC-AUC | F1 |
  |---|---|---|---|---|
  | Random guess | 0.139 | 0.084 | 0.500 | – |
  | Persistence rule | 0.598 | 0.260 | – | 0.560 |
  | Random Forest | 0.625 | 0.276 | 0.883 | 0.567 |
  | **GBT (chosen)** | **0.625** | **0.276** | **0.884** | 0.565 |

  The gain over persistence is small but real: +0.022 to +0.032 (block-bootstrap 95 % CI), better in 7 of 7 test years
  and 49 of 51 regions; spatial CV on held-out regions 0.606. Neighbour-cell heat is the most important input.
  Lakshadweep 2023: heatwave began 12 May, first warning 7 May (5 days ahead).
- **PostGIS:** cells, events, footprints and regimes loaded with GiST indexes; the example spatial queries in
  `sql/schema.sql` run in 1–2 s. The dashboard reads the exported files, so it needs no database server.
- Weak results, reported as such: K-Means regimes separate poorly (silhouette 0.26) and differ little between IOD
  phases; the strongest FP-Growth rules have lift ≈ 1.2.
- Known limits: the fixed 1991–2020 baseline turns the warming trend into near-permanent heatwave states (the longest
  "events" run 2014–16 and 2023–25); MEOW covers coasts and shelves only (half the cells are open ocean); when the water
  is still below the threshold, both the model and the rule are weak (PR-AUC ≈ 0.27).

## Course mapping

| Topic | Where |
|---|---|
| Spark big-data processing | Stages A–E on ~1 billion cell-days |
| Apache Sedona / spatial SQL | Region join (A), footprint geometry and `ST_Intersects` linking (C) |
| Map-reduce | Per-cell climatology, yearly aggregates |
| Data cleaning | Stage A (land/fill values, range check, duplicates) |
| Spatial database | PostGIS tables + `sql/schema.sql` queries |
| Partitioning | Lake by year and by cell bucket; GiST indexes |
| Clustering | DBSCAN (events), K-Means (regimes) |
| Classification | Random Forest / GBT onset model |
| Association rules | FP-Growth |
| Decision support / disaster case study | Dashboard risk layer; Lakshadweep 2023–24 |
