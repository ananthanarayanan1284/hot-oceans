# Hot Oceans (no coral) — 5-day plan

*18–22 Oct 2026. Replaces the coral parts of `IMPLEMENTATION_PLAN.md`; everything else there (machines, PostGIS setup, run log) still applies.*

**Title:** Hot Oceans: Spatiotemporal Detection, Tracking and Prediction of Marine Heatwaves across the Indian Ocean using Satellite SST Big Data, Apache Sedona and Spark MLlib

## What changed

Dropped: GCBD coral surveys, Allen Coral Atlas / Earth Engine, Coral Reef Watch, bleaching model.
New ML target: **will this cell enter a marine heatwave in the next 7 days?** Built from OISST alone, so there are millions of labelled rows and no survey cleaning.

## Data (only four sources)

| Source | Use | Size |
|---|---|---|
| NOAA OISST v2.1 daily 0.25°, via ERDDAP, box 30°S–30°N, 30–120°E, 1982–2025 | everything | ~6 GB raw, ~1B cell-days |
| MEOW marine ecoregions (shapefile) | region per cell, spatial CV folds | small |
| DMI (Indian Ocean Dipole), NOAA PSL | features, regime analysis | tiny |
| ONI (El Niño), NOAA CPC | features, regime analysis | tiny |

## Stages

| Stage | What | Syllabus item |
|---|---|---|
| A | NetCDF → long table → GeoParquet, partitioned by year and cell bucket; drop land/fill values, check duplicates; `cells` table + region (Sedona point-in-polygon join) into PostGIS | Spark, Sedona, cleaning, partitioning, PostGIS |
| B | Per-cell climatology + 90th-pct threshold (1991–2020, 11-day window, 31-day smoothing) with `groupBy(cell).applyInPandas` + numpy; Hobday detection (≥5 days, join gaps ≤2); categories | map-reduce, big-data processing |
| C | Daily DBSCAN on grid indices (eps ≈ 1.5 cells) → footprint polygons → day-to-day `ST_Intersects` linking → union-find → event catalogue (duration, area, intensity, track) → PostGIS `mhw_events` | clustering, spatial join |
| D | K-Means (k 3–8, elbow + silhouette) on event features → regimes; regime share by IOD/ENSO phase; FP-Growth on events, e.g. `{IOD+, Apr–May, Arabian Sea} ⇒ Severe` | clustering, association rules |
| E | Random Forest / GBT (Spark MLlib): features = today's anomaly, 7/30-day anomaly trend, past MHW days, month, region, DMI, ONI; label = MHW onset within 7 days. Sample non-events, use class weights. Evaluate with temporal holdout (train ≤2018, test 2019–2025) and spatial CV by ecoregion. Report PR-AUC, recall, F1, feature importance | classification |
| F | Case study: Lakshadweep 2023–24 heatwave as out-of-sample test (when did the model raise the alarm vs when the heatwave began) | disaster case study, decision support |
| G | Streamlit + pydeck dashboard on precomputed outputs (layout from the mockup, minus reef risk) | decision support |

## Day by day

| Day | Date | Work | Done when |
|---|---|---|---|
| 1 | 18 Oct | WSL: `.wslconfig` memory=12GB; conda env (Python 3.11, OpenJDK 17, pinned PySpark + Sedona); PostGIS in Docker; repo + `config.yaml`. **Start full OISST download** (yearly chunks, resumable). Download small dev box (lat 5–15, lon 65–80) first. Get MEOW, DMI, ONI | Sedona session starts; PostGIS answers; full download running |
| 2 | 19 Oct | Stage A on dev box, then full. Stage B on dev box; hand-check one Lakshadweep cell against the `marineHeatWaves` Python package. **Launch full Stage B overnight** | ~1B rows logged, no NaNs/duplicates; 2024 Lakshadweep MHW looks right |
| 3 | 20 Oct | Sanity plot: MHW days per year (expect peaks 1998, 2010, 2016, 2019–20, 2023–24). Stage C → event catalogue in PostGIS + track map | Event catalogue + figure |
| 4 | 21 Oct | Stage D (regimes, FP-Growth). Stage E (training table, RF/GBT, both CV schemes). Stage F case study | Metrics table, top rules, case-study figure |
| 5 | 22 Oct | Stage G dashboard; all figures; `run_log.csv` summary; report notes + limitations | Dashboard loads in seconds; deliverables ready |

## Fallbacks (decide early, not late)

- Download too slow by end of Day 1 → coarsen to 0.5° (4× fewer cells) or shrink the box; keep all years (baseline needs 1991–2020).
- Full Stage B > 8 h → run it one cell bucket at a time over two nights, or use 0.5°.
- DBSCAN too slow on 16k days → `scipy.ndimage.label` connected components inside `applyInPandas` (same result on a regular grid; say so in the viva).
- Model weak → report it honestly; compare against a persistence baseline ("anomaly above 0.8× threshold today").

## Evidence to log from Day 1

Every stage appends row counts, runtime, input/output size and partition count to `outputs/tables/run_log.csv`.
