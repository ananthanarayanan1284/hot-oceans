# Hot Oceans — Lessons from the basics

Step-by-step notes for understanding the Hot Oceans project, written for someone who knows ML and deep learning but is new to spatial big data.

**How to use this file**

- Read one lesson at a time, in order; each builds on the previous one.
- Every lesson has text "pictures" (diagrams in grey boxes), a worked example with real numbers from the project, ML/DL analogies, a summary and a quick check.
- In VS Code press `Ctrl+Shift+V` to read it formatted.
- Links like [hot_oceans/grid.py](hot_oceans/grid.py) open the matching code.

## Roadmap

| # | Lesson | One-line idea |
|---|---|---|
| 1 | Spatial data basics | data + location; grids (like images) and shapes |
| 2 | Where the data comes from | satellite temperature → files → one billion-row table |
| 3 | What a marine heatwave is | "hotter than normal for this place and date, for 5+ days" |
| 4 | Spark | many cores working on pieces of a huge table |
| 5 | Parquet and partitioning | how the billion rows are stored so each job reads only what it needs |
| 6 | Sedona spatial SQL | SQL that understands points and polygons |
| 7 | PostGIS | a spatial database to serve the small results |
| 8 | DBSCAN and tracking | hot cells → daily blobs → events that move through time |
| 9 | K-Means and FP-Growth | types of heatwaves; "if … then …" rules |
| 10 | The prediction model | week-ahead warning; leakage; honest evaluation |
| 11 | Results, dashboard, limitations | what was found and what is weak |
| 12 | Viva questions | short answers to practise |

## The whole project in one picture

```
 NOAA satellite sea temperature (1982–2025, daily, 0.25° grid)
        │  download one year at a time, check every day           (Lesson 2)
        ▼
 A  INGEST   grid → long table (cell, date, sst) → clean → Parquet lake   (Lessons 2, 4, 5)
        │    + every cell tagged with its sea region (spatial join)       (Lesson 6)
        ▼
 B  DETECT   per cell: "normal" + "unusually hot" curves → heatwave days + category   (Lesson 3)
        ▼
 C  EVENTS   per day: cluster hot cells (DBSCAN) → polygons → link day to day → events   (Lesson 8)
        ▼
 D  PATTERNS K-Means "regimes" of events; FP-Growth rules            (Lesson 9)
        ▼
 E  PREDICT  will this cell be in a heatwave within 7 days?          (Lesson 10)
        ▼
 F  CASE     Lakshadweep 2023: did the warning come before the heatwave?
        ▼
 G  SERVE    small files → PostGIS + Streamlit dashboard             (Lessons 7, 11)
```

---

# Lesson 1: Spatial data basics

## The lesson in one picture

```
 ordinary data            spatial data                 two ways to store it
 ─────────────            ────────────                 ─────────────────────
 "29.3 °C"        +  where? (10.6°N, 72.6°E)   →   RASTER  = grid of numbers (like an image)
                                                    VECTOR  = points, lines, polygons (shapes)
```

## 1.1 What makes data "spatial"?

Ordinary data says *what*. Spatial data also says *where*.

| Ordinary data | Spatial data |
|---|---|
| "Temperature = 29.3 °C" | "Temperature = 29.3 °C **at 10.6°N, 72.6°E**" |
| "A heatwave happened" | "A heatwave covered **this area** and moved **this way**" |

Once every value has a location, you can ask questions that ordinary tables can't answer easily:

```
 INSIDE?      Which cells are inside the "Maldives" sea region?        ┌─────┐
                                                                       │  •  │  point in polygon
                                                                       └─────┘
 OVERLAP?     Does today's heatwave shape overlap yesterday's?         ┌───┐
                                                                       │ ┌─┼─┐
                                                                       └─┼─┘ │  two polygons overlap
                                                                         └───┘
 NEAR?        Which events were within 300 km of Lakshadweep?          • ←300 km→ •

 MOVE?        Where did the heatwave's centre go, day by day?          •──•──•──•→
```

These need special **spatial** tools (Sedona, PostGIS). That's what the course is about.

## 1.2 Latitude and longitude

Every place on Earth has two numbers:

```
                 90°N (North Pole)
                     │
      latitude  ─────┼──────  0° = equator
      (north/south)  │
                 90°S (South Pole)

      longitude: 0° at Greenwich (London), up to 180° east or west
```

- **Latitude**: north–south position, −90° to +90°. Negative = south (e.g. 30°S = −30).
- **Longitude**: east–west position, −180° to +180°. The Indian Ocean is east (positive).
- **1° of latitude ≈ 111 km** everywhere.

The project's areas:

```
  lat
  30°N ┌────────────────────────────────────────────────┐
       │  Arabian      India     Bay of                  │
       │  Sea   ┌──────┐         Bengal                  │
  15°N │        │ dev  │                                 │
       │        │ box ★│  ★ = Lakshadweep (10.57°N, 72.64°E)
   5°N │        └──────┘                                 │
   0°  │ Africa         Equatorial Indian Ocean  Indonesia│
       │                                                 │
       │   South-west               South-east           │
  30°S └────────────────────────────────────────────────┘
       30°E          65° 80°E                       120°E   lon

  FULL box: 30°S–30°N, 30°E–120°E (the whole tropical Indian Ocean)
  DEV box:  5°N–15°N, 65°E–80°E   (small test area around Lakshadweep)
```

## 1.3 Raster data: a grid, exactly like an image

A **raster** cuts the world into equal squares and stores one number per square.

```
   one day of sea temperature (°C), a tiny 4×5 corner of the grid

            72.125  72.375  72.625  72.875  73.125   ← longitude of square centre
   10.875 │  29.0    29.1    29.2    29.2   land   │
   10.625 │  29.1    29.3    29.3    29.4   land   │
   10.375 │  29.0    29.2    29.4    29.5   29.6   │
   10.125 │  28.9    29.1    29.3    29.4   29.5   │
     ↑ latitude of square centre
```

ML analogy: **a raster is an image**. Each pixel holds a temperature instead of a colour.

In this project:

- Each square ("**cell**") is **0.25° × 0.25°** ≈ 28 km × 28 km near the equator.
- The full box is **240 rows** (60° ÷ 0.25) × **360 columns** (90° ÷ 0.25) = 86,400 squares.
- Land squares have no sea temperature → dropped → **58,334 ocean cells**.
- One "image" per day for **16,071 days** (1 Jan 1982 – 31 Dec 2025).

So the data is really a **video**:

```
          day 16,071 ┌───────────┐
                  ⋮ ┌───────────┐│
          day 2   ┌───────────┐│┘      shape = [days, rows, cols]
          day 1  ┌───────────┐│┘              = [16071, 240, 360]
                 │ 240 × 360 │┘
                 │  °C grid  │
                 └───────────┘
```

The model-lab script ([experiments/model_lab.py](experiments/model_lab.py)) literally loads the data as a numpy array `[day, row, col]`.

## 1.4 Vector data: shapes

```
 POINT        •                    one location            e.g. centre of a cell
 LINE         •───•───•───•        a path                  e.g. a heatwave's track
 POLYGON      ┌──────┐             an area with a border   e.g. a sea region, a heatwave's shape
              │      │
              └──────┘
```

## 1.5 The project uses both

| Thing in the project | Type | Example |
|---|---|---|
| Daily sea temperature per cell | Raster | 29.3 °C at cell 579170 on 1 May 2023 |
| Centre of each cell | Point | POINT (72.625 10.625) |
| Each cell's square | Polygon | the 0.25° square around that point |
| Marine ecoregions | Polygons | "Maldives", "Western India" |
| A heatwave's shape on one day ("footprint") | Polygon | a blob over the Arabian Sea |
| The path a heatwave moved along | Line | centre on each day, joined |

A key step of the pipeline is **raster → vector**: a group of hot grid squares becomes one polygon.

```
  hot cells on one day (raster)            footprint (vector polygon)
  . . . . . . .                            . . . . . . .
  . # # # . . .                            . ┌─────┐ . .
  . # # # # . .           ───────►         . │     └─┐ .
  . . # # # . .                            . └─┐     │ .
  . . . . . . .                            . . └─────┘ .
```

Once heatwaves are polygons, you can ask "does today's shape overlap yesterday's?" — that's how heatwaves are tracked (Lessons 6 and 8).

## 1.6 Giving each cell an ID number

Pairs like (10.625, 72.625) are clumsy as keys, so each cell gets one integer. It's the same trick as flattening an image:

```
   world grid: 720 rows (−90 … +90) × 1440 columns (0 … 360°), each 0.25°

   row     = floor( (lat + 90) / 0.25 )
   col     = floor( lon / 0.25 )
   cell_id = row × 1440 + col            ← like index = row × width + col for pixels
```

**Worked example — Lakshadweep (10.57°N, 72.64°E):**

```
   row     = floor( (10.57 + 90) / 0.25 ) = floor(402.28) = 402
   col     = floor( 72.64 / 0.25 )        = floor(290.56) = 290
   cell_id = 402 × 1440 + 290             = 579,170
```

This is exactly the case-study cell `579170` in the results.

**Going back** (cell id → centre of the square):

```
   row = 579170 // 1440 = 402          lat = −90 + (402 + 0.5) × 0.25 = 10.625
   col = 579170 %  1440 = 290          lon =       (290 + 0.5) × 0.25 = 72.625
```

Because the IDs index the **whole world's** grid, the dev and full runs share the same IDs. Code: [hot_oceans/grid.py](hot_oceans/grid.py) (`cell_id`, `row_col`, `center`), checked by a unit test (`test_grid_roundtrip`).

## 1.7 Two more terms

### CRS: the "unit system" of coordinates

A **Coordinate Reference System** says what the numbers mean. The project uses plain latitude/longitude in degrees: **EPSG:4326** (`crs=4326` in the code). Other CRSs use metres (e.g. UTM), but this project stays in degrees.

### Cells get smaller away from the equator

Lines of longitude meet at the poles, so a 0.25° square is narrower further from the equator:

```
   at the equator:  ┌────────────┐   27.8 km wide
   at 30°S:          ┌──────────┐    24.1 km wide  (× cos 30° = 0.87)
```

```
   area = (0.25 × 111.32 km)² × cos(latitude)
   equator: 27.83² × 1.000 = 774 km²
   30°S:    27.83² × 0.866 = 671 km²
```

When the project adds up heatwave area, it uses each cell's real area (`cell_area_km2` in grid.py), not a simple count of cells.

## Summary of Lesson 1

- Spatial data = data + location (latitude, longitude in EPSG:4326).
- **Raster** = grid of numbers, like an image; the sea temperature is a "video" of 16,071 daily frames of 240×360.
- **Vector** = points, lines, polygons: cells, regions, heatwave shapes and tracks.
- Each cell has an integer ID: `row × 1440 + col` (Lakshadweep = 579,170).
- Cells shrink with latitude; areas are corrected with cos(latitude).

**Quick check**

1. Is a heatwave's daily footprint raster or vector? *Answer: vector (a polygon).*
2. What is the cell ID of a point at 0.1°N, 80.1°E? *Answer: row = floor(90.1/0.25) = 360, col = floor(80.1/0.25) = 320, id = 360 × 1440 + 320 = 518,720.*

---

# Lesson 2: Where the data comes from, and how a map becomes a table

## The lesson in one picture

```
  satellites + ships + buoys
           │  blended and gap-filled by NOAA
           ▼
  OISST v2.1  (daily, 0.25°, whole world, 1981 → today)
           │  OPeNDAP: download only the Indian Ocean box, one month at a time
           ▼
  44 NetCDF files  oisst_1982.nc … oisst_2025.nc   (≈1.6 GB)
           │  check: same number of ocean cells every day?
           ▼
  Stage A: grid → long table → clean
           ▼
  937,485,714 rows:  cell_id | date | sst
```

## 2.1 What is SST?

**SST = Sea Surface Temperature**: the temperature of the top layer of the ocean. It is the **only** measured variable in the project. Heatwaves, events and the prediction model are all built from SST.

## 2.2 How SST is measured

```
        🛰  satellite (infrared sensor, "AVHRR")
         \     measures heat given off by the sea surface
          \    ✗ can't see through clouds
           ▼
   ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ sea surface ~~~~~~~~~~~~~~~~~~~~
      🚢 ships      ⚓ buoys      🤖 Argo floats   (direct measurements)
```

Satellites see the whole ocean but miss cloudy places and drift slightly in calibration. Ships and buoys are accurate but sparse. NOAA **blends** both and fills the gaps with a statistical method called **Optimum Interpolation**. The product is **OISST v2.1**:

| Property | Value |
|---|---|
| Time step | daily |
| Grid | 0.25° (≈ 28 km) |
| Coverage | whole world |
| Period | September 1981 → today |
| Gaps | none (every ocean cell, every day) |

ML analogy: someone has already done careful **imputation** of all missing values using physics and statistics. That's why OISST is the standard dataset for heatwave research.

## 2.3 The three small extra datasets

| Dataset | What it is | Size | Used for |
|---|---|---|---|
| **MEOW** (Marine Ecoregions of the World) | polygons of named coastal/shelf sea regions | small shapefile | label each cell with a region; spatial CV folds |
| **DMI** (Dipole Mode Index) | one number per month: Indian Ocean Dipole state | tiny text file | pattern analysis (Lesson 9) |
| **ONI** (Oceanic Niño Index) | one number per month: El Niño / La Niña state | tiny text file | pattern analysis (Lesson 9) |

Downloaded by [pipeline/download_aux.py](pipeline/download_aux.py) into `data/aux/`.

## 2.4 The file format: NetCDF

Gridded climate data is stored in **NetCDF** (`.nc`) files. Think of a NetCDF file as a **numpy array with labelled axes**:

```
   oisst_2023.nc
   └── sst [time, lat, lon]          values in °C (NaN on land)
        ├── time: 365 values   2023-01-01 … 2023-12-31
        ├── lat : 240 values   -29.875 … 29.875
        └── lon : 360 values    30.125 … 119.875
```

```
            lon →
         ┌──────────┐
   lat ↓ │  °C grid │   × 365 days   = a 3-D cube [365, 240, 360]
         └──────────┘
```

ML analogy: a tensor `[365, 240, 360]` whose axes carry real coordinates. Python reads it with **xarray** (pandas for multi-dimensional arrays). One file per year: 44 files, ≈ 36 MB each, ≈ 1.6 GB in total (compressed).

## 2.5 Downloading with OPeNDAP

NOAA's yearly file covers the **whole world** (1440 × 720 cells). We only need the Indian Ocean box. **OPeNDAP** lets you open a file on a server **as if it were local** and transfer only a slice:

```python
url = "https://psl.noaa.gov/thredds/dodsC/Datasets/noaa.oisst.v2.highres/sst.day.mean.2023.nc"
ds  = xr.open_dataset(url)                                   # nothing downloaded yet, only the "table of contents"
box = ds["sst"].sel(lat=slice(-30, 30), lon=slice(30, 120))  # still nothing downloaded
box.load()                                                    # NOW only the box is transferred
```

```
   whole world on the server                     what is downloaded
   ┌────────────────────────────┐
   │                            │
   │        ┌──────┐            │    ───►       ┌──────┐
   │        │ box  │            │               │ box  │   (≈ 1/30 of the world)
   │        └──────┘            │               └──────┘
   └────────────────────────────┘
```

[pipeline/download_oisst.py](pipeline/download_oisst.py) requests **one month at a time** (smaller requests fail less often), retries failures, and writes each year to a `.part` file that is renamed only when the year is complete. Finished years are skipped, so the download can resume.

## 2.6 The silent-corruption story (good viva story)

On the DGX server, 4 downloads were run **in parallel** to save time. Some network streams dropped **without raising any error**, and the server returned **half-empty months**.

How it was caught — the land never moves, so every day must have the **same number of ocean cells**:

```
   valid ocean values per day (full box)

   58,334 ┤████████████████  ██████████████████████████████
          │                ██
   ~29k   ┤                ██   ← a broken day: half the cells missing
          │
        0 ┼───────────────────────────────────────────────── day
```

Result: **162 bad days** (five whole Januaries — 1984, 1986, 1994, 2011, 2015 — plus 7 first-of-month days). The first full run (3 Nov) had been built on this broken data.

Fixes:

1. `download_oisst.py` now checks **every month**: same ocean count every day and no values outside −2 … 40 °C; bad months are fetched again.
2. [dgx/check_raw.py](dgx/check_raw.py) checks all files before processing (and can delete bad years).
3. Downloads now run **one at a time**; everything was rebuilt on 4 Nov ([dgx/redo_full.sh](dgx/redo_full.sh)).

Moral: **data validation matters as much as computing power.**

## 2.7 Map → table: the "long format" (Stage A)

A grid is convenient for maps, but Spark and SQL work with **tables**. Stage A "unrolls" every grid cell of every day into one row:

```
   GRID for 2023-05-01                         LONG TABLE
             lon 72.375  lon 72.625            cell_id   date        sst
   lat 10.625   29.1        29.3       ───►    579169    2023-05-01  29.1
   lat 10.375   29.0        NaN (land)         579170    2023-05-01  29.3
                                               578729    2023-05-01  29.0
                                               (land cell dropped)
```

Each row is one **cell-day** (one cell on one day). How many?

```
   58,334 ocean cells × 16,071 days = 937,485,714 rows   (almost 1 billion)
   per year: 58,334 × 365 ≈ 21.3 million rows
```

ML analogy: like turning an image dataset into a CSV with one row per pixel per image. Wasteful for a CNN, but it makes SQL-style work easy: "group by cell", "join with regions", "filter dates", at scale.

## 2.8 Cleaning (Stage A)

[pipeline/stage_a_ingest.py](pipeline/stage_a_ingest.py), function `read_year`, for each year file:

```
   NetCDF year ──► to table ──► 1. drop NaN (land)
                               2. keep −2 °C ≤ sst ≤ 40 °C   (seawater can't be colder or hotter)
                               3. drop duplicate (cell_id, date)
                               4. add cell_id (Lesson 1) and cell_bucket (Lesson 5)
                               ──► Parquet
```

After all years, a **lake check** counts the whole table:

| Check | Result (full run) |
|---|---|
| rows | 937,485,714 |
| duplicate (cell_id, date) | 0 |
| null sst | 0 |

This is logged in `outputs/full/tables/run_log.csv` as evidence.

Stage A also builds the **cells table**: one row per ocean cell with its centre point, its square polygon, area, sector and MEOW ecoregion (the spatial join is explained in Lesson 6).

## 2.9 Two sizes: dev and full

| | dev | full |
|---|---|---|
| Area | 5–15°N, 65–80°E (around Lakshadweep) | 30°S–30°N, 30–120°E |
| Ocean cells | 1,971 | 58,334 |
| Rows | 31.7 million | 937.5 million |
| Years | all 44 | all 44 |
| Runs on | the laptop (PC) | the DGX server |

Why keep all 44 years in dev mode? The heatwave definition needs **30 years of "normal" (1991–2020)** to compare against (Lesson 3).

ML analogy: debugging your training loop on a small subset before launching the full run on a GPU cluster. The same code runs both; only `--mode dev` or `--mode full` changes ([config.yaml](config.yaml)).

## Summary of Lesson 2

- **SST** from satellites + ships + buoys → NOAA **OISST**: daily, 0.25°, gap-free.
- Stored as **NetCDF** (labelled 3-D array), downloaded by slice with **OPeNDAP**, one month at a time.
- Parallel downloads silently broke 162 days; the "same ocean count every day" check caught it.
- Stage A unrolls the grid into a **long table** of 937.5 M cell-days and cleans it (land, range, duplicates): 0 duplicates, 0 nulls.
- dev box for testing on the PC, full box on the DGX.

**Quick check**

1. Why does each day have the same number of ocean cells? *Answer: the land mask never changes.*
2. How many rows does one year of the dev box have? *Answer: 1,971 × 365 ≈ 719,000.*

---

# Lesson 3: What is a marine heatwave?

## 3.1 Why "hot" can't be one fixed number

Suppose a heatwave were "sea temperature above 30 °C". It fails:

- Near the equator, 30 °C is a **normal** day.
- Off South Africa in winter, 22 °C might be **extremely** hot for that place.
- Even in one place, 29 °C is normal in May but unusual in January.

So "hot" must mean **hotter than what is normal for this place at this time of year**.

ML analogy: like **normalising each feature separately**, here per location *and* per day of the year, so every cell is compared only with its own history.

## The whole lesson in one picture

Everything in this lesson is five steps, done separately for every ocean cell:

```
 STEP 1  Look at the past (1991–2020)      → what is "normal" for this place on this date?
            │
 STEP 2  Two curves for the year            → climatology (normal) and threshold (unusually hot)
            │
 STEP 3  Compare today's SST                → anomaly = SST − climatology (how far above normal)
            │
 STEP 4  The 5-day rule                     → above the threshold 5+ days in a row? → HEATWAVE
            │
 STEP 5  The ratio ladder                   → how many "gaps" above normal? → Moderate … Extreme
```

Sections 3.2–3.5 explain each step slowly, and 3.5 ends with one worked example that goes through all five.

## 3.2 Climatology: the "normal" for each cell and day (Steps 1–2)

### The question

> "Is 29.8 °C at Lakshadweep on 1 May **hot**?"

You can't answer without knowing **what 1 May is usually like at Lakshadweep**. That "usual" value is the **climatology**.

### Step 1a: collect past values for the same date

A toy version with only 5 years:

| Year | SST on 1 May |
|---|---|
| 1991 | 29.1 |
| 1992 | 29.4 |
| 1993 | 28.9 |
| 1994 | 29.6 |
| 1995 | 29.0 |

Average = (29.1 + 29.4 + 28.9 + 29.6 + 29.0) / 5 = **29.2 °C** → the "normal" 1 May temperature for this place.

### Step 1b: why ±5 days? (the 11-day window)

The project uses **30 years** (1991–2020), which gives only 30 values for 1 May. That's too few to find the "top 10%" reliably (it would rest on just the 3 hottest values).

But 30 April or 2 May are almost the same as 1 May; the sea changes slowly. So for every year, take **26 April to 6 May** (1 May ± 5 days = 11 days):

```
   one year:   26 27 28 29 30 [1] 2  3  4  5  6     ← 11 days around 1 May
                         ×
   30 years (1991 … 2020)
                         =
   330 values that all describe "a normal 1 May"
```

More samples give a more stable estimate. ML analogy: like **data augmentation**, borrowing nearby, almost-identical samples.

### Step 1c: two numbers from the 330 values

Here's a made-up spread of the 330 values (a histogram drawn sideways):

```
 SST range (°C)   how many of the 330 values
 28.6 – 28.8      ▇▇▇                          10
 28.8 – 29.0      ▇▇▇▇▇▇▇▇▇▇▇▇                  45
 29.0 – 29.2      ▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇          80
 29.2 – 29.4      ▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇           75   ← MEAN ≈ 29.3 °C  = CLIMATOLOGY ("normal")
 29.4 – 29.6      ▇▇▇▇▇▇▇▇▇▇▇▇▇                 50
 29.6 – 29.8      ▇▇▇▇▇▇▇▇▇                     37
                  ─────────────────────────────────  ← 90th PERCENTILE ≈ 29.8 °C = THRESHOLD
 29.8 – 30.0      ▇▇▇▇▇▇▇▇                      33      (only these 10% are hotter)
```

- **Mean** of the 330 values → the **climatology** = what a normal 1 May looks like.
- **90th percentile** → the **threshold**. Sort the 330 values; the value at position 297 (90% of 330) is the threshold. Only 10% of normal 1 Mays are hotter than this, so anything above it is **unusually hot**.

In this example, 29.8 °C on 1 May is right at the "unusually hot" line.

### Step 2a: repeat for every day of the year → two curves

Do steps 1a–1c for 2 May, 3 May, … every calendar day. You get **two curves** per cell:

```
 °C
 30.0 |            . - - - - .                       ← THRESHOLD (90th percentile)
      |        . -             - .
 29.5 |     .-       _______       - .
      |   .-     .--         --.      -.             ← CLIMATOLOGY (normal)
 29.0 | .-    .--               --.      -.
      |-   .--                     --.     - .
 28.5 |.--                             --.     - . _
      +----+------+------+------+------+------+------
          Jan    Mar    May    Jul    Sep    Nov
```

- The **threshold** curve always sits above the **climatology** curve.
- At Lakshadweep both peak around April–May (the warmest time of year there).
- The distance between the two curves is the **gap**, used later for categories (3.5).

### Step 2b: smoothing (31-day moving average)

Raw curves are jagged by chance (e.g. 1 May = 29.20, 2 May = 29.26, 3 May = 29.17). The real "normal" changes smoothly through the year, so each day's value is replaced by the **average of the 31 days around it** (15 before, the day itself, 15 after).

```
 before smoothing:  /\/\_/\/\/\_/\/\/\       after smoothing:   ___/‾‾‾‾‾\___
```

ML analogy: a moving-average filter, like smoothing a noisy loss curve.

### Step 2c: do it for every cell

All of this is for **one cell**. Stage B repeats it for **all 58,334 cells**, because "normal" differs everywhere. Each cell gets its own two curves of 366 values.

### The 29 February detail

Leap years have 366 days. If days were simply numbered 1–365, 1 March would be day 60 in a normal year but day 61 in a leap year, so dates wouldn't line up. The project always uses a **366-day calendar** where day 60 = 29 February (empty in normal years). So "day 122" is always 1 May. A unit test checks this.

Code: `climatology()` in [hot_oceans/hobday.py](hot_oceans/hobday.py).

## 3.3 Anomaly

**Anomaly = today's SST − climatology for today.**

- +1.2 °C means 1.2 degrees warmer than normal for this place and date.
- It is the most useful number in the project; most model features are built from anomalies.

## 3.4 The heatwave rule (Hobday et al., 2016)

The **international standard definition**:

> A marine heatwave is when SST stays **above the 90th-percentile threshold for at least 5 days in a row**. If two heatwaves are separated by a gap of **2 days or less**, they count as one.

Example timeline (✔ = above threshold, ✘ = below):

```
Day:     1  2  3  4  5  6  7  8  9 10 11 12 13 14 15 16 17 18
Above:   ✔  ✔  ✔  ✘  ✘  ✔  ✔  ✔  ✔  ✔  ✔  ✘  ✘  ✔  ✔  ✔  ✔  ✔
```

- Days 1–3: only 3 days → **not a heatwave**, just a hot spell.
- Days 6–11: 6 days → **a heatwave**.
- Days 12–13: a 2-day gap.
- Days 14–18: 5 days → also a heatwave, and the gap is ≤2 days, so **days 6–18 are one heatwave**. The gap days count as heatwave days too.

Why 5 days? To ignore short blips. Why join gaps? So one event isn't split by a brief cool-down.

## 3.5 Categories: how severe? (Step 5, Hobday et al., 2018)

Like hurricane categories (1–5), heatwaves get categories 1–4.

### The ruler: the "gap"

To measure "how bad", use the distance between **normal** and **unusually hot** as a ruler:

```
gap   = threshold − climatology
ratio = anomaly / gap  = (SST − climatology) / (threshold − climatology)
```

The **ratio** says: *how many gaps above normal is today?*

### Picture: the ladder

Example: climatology = 29.0 °C, threshold = 29.5 °C, so gap = 0.5 °C. Each rung of the ladder is one gap (0.5 °C) higher:

```
  SST (°C)    ratio
  31.0  ┬──── 4  ─────────────────────────
        │         above 31.0 → 4 EXTREME
        │
        │   30.5 – 31.0      → 3 SEVERE
  30.5  ┼──── 3  ─────────────────────────
        │   30.0 – 30.5      → 2 STRONG
  30.0  ┼──── 2  ─────────────────────────
        │   29.5 – 30.0      → 1 MODERATE
  29.5  ┼──── 1  ─────────────────────────   ← THRESHOLD (90th percentile)
        │   29.0 – 29.5      → warmer than normal, but not unusual
  29.0  ┴──── 0  ─────────────────────────   ← CLIMATOLOGY (normal)
```

| ratio | Category |
|---|---|
| below 1 | not above the threshold |
| 1 to <2 | 1 Moderate |
| 2 to <3 | 2 Strong |
| 3 to <4 | 3 Severe |
| 4 or more | 4 Extreme |

In code: `category = floor(ratio)`, limited to 1–4, and only on heatwave days.

### The two examples, step by step

**SST = 29.7 °C**

1. anomaly = 29.7 − 29.0 = **0.7 °C**
2. ratio = 0.7 / 0.5 = **1.4**
3. 1.4 is between 1 and 2 → **1 Moderate** (on the ladder: between 29.5 and 30.0)

**SST = 30.6 °C**

1. anomaly = 30.6 − 29.0 = **1.6 °C**
2. ratio = 1.6 / 0.5 = **3.2**
3. 3.2 is between 3 and 4 → **3 Severe** (on the ladder: between 30.5 and 31.0)

### Why divide by the gap instead of just using the anomaly?

Because places differ in how much their temperature normally swings. Two places, both **+1.0 °C** above normal:

| | Place A: steady tropical sea | Place B: very variable sea |
|---|---|---|
| climatology | 29.0 | 20.0 |
| threshold | 29.3 | 22.0 |
| gap | **0.3** | **2.0** |
| anomaly | +1.0 | +1.0 |
| ratio | 1.0 / 0.3 = **3.3 → Severe** | 1.0 / 2.0 = **0.5 → not even above the threshold** |

```
 Place A (small gap):  normal ├─┼─┼─┼─┤ +1.0 °C climbs 3 rungs → Severe
 Place B (big gap):    normal ├──────────┼──── +1.0 °C is only half a rung → nothing
```

The same +1 °C is **severe** where the sea is normally steady, but **ordinary** where it swings a lot. Dividing by the gap makes "Severe" mean the same thing everywhere.

ML analogy: it's like a **z-score**, dividing by a measure of spread so values from different places become comparable.

### Two small points

1. A category is given **only on heatwave days** (Step 4: 5+ days above the threshold). A single hot day with ratio 3.2 but no heatwave gets category **0**.
2. **Gap days inside a heatwave** (the ≤2 cool days that get joined, 3.4) can have a ratio below 1. They still get category 1, because the category is clipped to 1–4 on heatwave days.

### Worked example: all five steps together

One cell, 10 days in May. Climatology = 29.0 °C and threshold = 29.5 °C on these days (gap = 0.5).

| Day | SST | Anomaly | Ratio | Above threshold? | Days in a row | Heatwave? | Category |
|---|---|---|---|---|---|---|---|
| 1 | 29.3 | +0.3 | 0.6 | no | 0 | no | 0 |
| 2 | 29.6 | +0.6 | 1.2 | yes | 1 | **yes** | 1 Moderate |
| 3 | 29.9 | +0.9 | 1.8 | yes | 2 | **yes** | 1 Moderate |
| 4 | 30.2 | +1.2 | 2.4 | yes | 3 | **yes** | 2 Strong |
| 5 | 30.6 | +1.6 | 3.2 | yes | 4 | **yes** | 3 Severe |
| 6 | 30.8 | +1.8 | 3.6 | yes | 5 | **yes** | 3 Severe |
| 7 | 30.4 | +1.4 | 2.8 | yes | 6 | **yes** | 2 Strong |
| 8 | 29.7 | +0.7 | 1.4 | yes | 7 | **yes** | 1 Moderate |
| 9 | 29.4 | +0.4 | 0.8 | no | 0 | no | 0 |
| 10 | 29.2 | +0.2 | 0.4 | no | 0 | no | 0 |

Days 2–8 are above the threshold 7 days in a row (≥ 5), so they form **one heatwave**, and each of its days gets a category from its ratio. The heatwave's **peak category is Severe** (days 5–6).

The same thing as a picture (bar length = ratio; `|` marks the ladder rungs):

```
           ratio  0    1    2    3    4
                  |    |    |    |    |
 Day 1   0.6      ███                            below threshold → 0
 Day 2   1.2      ██████                         Moderate  ┐
 Day 3   1.8      █████████                      Moderate  │
 Day 4   2.4      ████████████                   Strong    │
 Day 5   3.2      ████████████████               Severe    │ 7 days in a row
 Day 6   3.6      ██████████████████             Severe    │ above threshold
 Day 7   2.8      ██████████████                 Strong    │ = ONE HEATWAVE
 Day 8   1.4      ███████                        Moderate  ┘
 Day 9   0.8      ████                           below threshold → 0
 Day 10  0.4      ██                             below threshold → 0
```

Note the hindsight (3.6): on **day 2** you can't yet know it's a heatwave, because the sea has been hot for only 1 day. Only on **day 6** (5 days reached) does it become one, and then days 2–5 are labelled too, looking back.

Each cell-day gets its `category` (0–4) in Stage B's output table `sst_anom`. In the full run, **7.2% of all cell-days** were heatwave days.

**Quick check:** climatology = 28.0, threshold = 28.4, SST = 29.3, and it's a heatwave day. Category?
*Answer: gap 0.4, anomaly 1.3, ratio 3.25 → 3 Severe.*

## 3.6 The "hindsight" problem (it caused the model leak)

In the timeline above, **on day 6 itself you don't yet know** it's a heatwave: the sea has only been hot for 1 day. It becomes a heatwave only when day 10 arrives (5 days reached). The category is assigned **looking back**, with hindsight.

That's fine for *describing the past*, but dangerous for *prediction*:

- The old onset model used inputs such as "are my neighbours in a heatwave today?" and chose its rows with the heatwave flag. That flag secretly contained information about the next 4 days.
- ML analogy: classic **look-ahead (target) leakage**, like using a feature computed after the event you're predicting.

On 8 Nov 2026 this was found with `experiments/model_lab.py` and Stage E was rebuilt (Lesson 10). The rebuilt model was run on the full basin on the DGX on 9 Nov 2026, and the report and presentation now use those leak-free numbers (Lesson 10.10).

## 3.7 Fixed vs moving baseline

Everything is compared with **1991–2020** (the official WMO "normal" period). But the ocean keeps warming:

- In 2024 the sea was warmer than the 1991–2020 average almost everywhere.
- So the threshold is crossed very often: in 2024 the average cell was in a "heatwave" for **133 days**.

The debate:

- **Fixed baseline** (used here): shows what ecosystems actually experience. Corals don't care whether the heat is "trend" or "extreme".
- **Moving / detrended baseline**: separates short extreme events from long-term warming.

The report lists this as a limitation; it also explains why some "events" last 2–3 years.

## 3.8 Climate drivers: El Niño and the Indian Ocean Dipole

Natural see-saws of the ocean–atmosphere system that make whole regions warmer or cooler for months.

- **ENSO (El Niño / La Niña)**: centred in the Pacific but affects the whole tropics. During **El Niño**, most of the Indian Ocean warms a few months later. Index: **ONI**; ≥ +0.5 = El Niño, ≤ −0.5 = La Niña.
- **IOD (Indian Ocean Dipole)**: the Indian Ocean's own west–east see-saw. **Positive IOD** = warm west (Arabian Sea, East Africa), cool east (Indonesia); negative = the opposite. Index: **DMI**; ≥ +0.4 = positive, ≤ −0.4 = negative.

The big heatwave years in the results (1998, 2010, 2016, 2023–24) line up with strong El Niño and/or positive IOD years.

## 3.9 Why it matters

- Heatwaves cause **coral bleaching**: corals expel their algae under heat stress and can die. Lakshadweep reefs were badly hit in 2023–24, hence the case study.
- They also affect fisheries and seagrass, and influence the Indian monsoon.

## 3.10 Where this lives in the project

- [hot_oceans/hobday.py](hot_oceans/hobday.py): `climatology()` (3.2) and `detect()` (3.4 + 3.5). Plain numpy, about 80 lines.
- [pipeline/stage_b_detect.py](pipeline/stage_b_detect.py): runs this for all 58,334 cells using Spark (Lessons 4–5).
- Settings in [config.yaml](config.yaml) under `hobday:` and `baseline:`.

## Summary of Lesson 3

- "Hot" is relative to each cell's own **climatology** (the 1991–2020 normal for that calendar day).
- **Threshold** = 90th percentile from an 11-day window × 30 years, smoothed.
- **Anomaly** = SST − climatology.
- **Heatwave** = above the threshold for ≥5 days; gaps of ≤2 days are joined.
- **Category** = anomaly ÷ (threshold − climatology): Moderate, Strong, Severe, Extreme.
- Heatwave labels are assigned **with hindsight**, which caused the old model's leak.
- A fixed baseline + warming gives very many heatwave days recently.
- **El Niño (ONI)** and the **IOD (DMI)** are the big climate drivers.

**Quick check:** the sea is above the threshold for 4 days, cool for 1 day, then above it for 3 days. Is this a heatwave?
*Answer: no. Joining only merges runs that are each already ≥5 days, and here neither run reaches 5.*

---

# Lesson 4: Why "big data", and what Spark is

## The lesson in one picture

```
   pandas (one worker)                         Spark (many workers)
   ───────────────────                         ────────────────────
   ┌──────────────────────┐                    ┌────┐┌────┐┌────┐┌────┐
   │ the WHOLE table must │                    │part││part││part││part│ … many partitions
   │ fit in RAM           │                    └─┬──┘└─┬──┘└─┬──┘└─┬──┘
   │ 1 CPU core           │                      ▼     ▼     ▼     ▼
   └──────────────────────┘                    core1 core2 core3 core4 … (48 on the DGX)
   937 M rows → out of memory                  each core handles one piece at a time
```

## 4.1 Why pandas isn't enough

After Stage B, every row has about 10 columns (sst, climatology, threshold, anomaly, ratio, category…).

```
   937,485,714 rows × 10 columns × 4 bytes ≈ 37.5 GB   (plus pandas overhead → more)
   laptop RAM ≈ 16 GB                                    → doesn't fit
```

Three problems:

1. **Memory**: the table doesn't fit in RAM.
2. **Speed**: pandas uses one CPU core.
3. **Regrouping**: some steps need the data grouped **by cell** (a time series), others **by day** (a map). Regrouping a billion rows is heavy.

You need a tool that works on data bigger than memory, uses many cores, and regroups efficiently: **Apache Spark**.

ML analogy: going from training on one batch in memory to a **data-parallel** setup with many workers and a data loader that streams from disk.

## 4.2 What Spark is

Spark is a **distributed data-processing engine**. You write code that looks like pandas or SQL; Spark splits the work across many cores (or many computers).

```
                 ┌────────────────────────┐
                 │  DRIVER (your script)  │   plans the work, collects results
                 └───────────┬────────────┘
           ┌─────────────────┼─────────────────┐
           ▼                 ▼                 ▼
     ┌──────────┐      ┌──────────┐      ┌──────────┐
     │ task on  │      │ task on  │      │ task on  │   each task processes
     │partition1│      │partition2│      │partition3│   ONE piece of the data
     └──────────┘      └──────────┘      └──────────┘
```

- **Driver**: the main Python program. It builds the plan.
- **Tasks / executors**: workers that each process one **partition**.
- **Partition**: one piece of a table. A table is split into many partitions.

This project runs Spark in **local mode**: one machine, many cores.

| Setting | PC (laptop) | DGX (server) |
|---|---|---|
| `master` | `local[8]` = 8 cores | `local[48]` = 48 of 256 shared cores |
| driver memory | 6 GB | 200 GB |
| shuffle partitions | 32 | 384 |

The same code runs on both; only [config.yaml](config.yaml) changes. The session is created in [hot_oceans/spark.py](hot_oceans/spark.py), with Sedona switched on (Lesson 6).

## 4.3 Lazy evaluation: plan first, run later

```python
df  = spark.read.parquet("lake/sst_anom")           # transformation: nothing runs
hot = df.filter("category > 0")                     # transformation: nothing runs
n   = hot.groupBy("year").count()                   # transformation: nothing runs
n.write.parquet("out")                              # ACTION: now everything runs
```

```
   read ──► filter ──► groupBy/count ──► write
   └──────── a plan (graph) ────────┘     └── action triggers execution
```

- **Transformations** (`filter`, `select`, `join`, `groupBy`) only add steps to a plan.
- **Actions** (`count`, `write`, `toPandas`) execute the plan.
- Before running, Spark's optimiser (**Catalyst**) improves the plan, e.g. reads only the needed columns and applies filters as early as possible.

ML analogy: building a computation graph (TensorFlow graph mode, `torch.compile`) and executing it once, optimised.

## 4.4 Shuffle: the expensive part

`groupBy("cell_id")` needs **all rows of a cell together**. If a cell's rows are spread over many partitions, Spark must move them:

```
   BEFORE (rows spread around)                 AFTER SHUFFLE (grouped by cell)
   partition 1: A B C A                        partition 1: A A A A
   partition 2: B C A B          ───────►      partition 2: B B B B
   partition 3: C A B C       data written     partition 3: C C C C
                              to disk and
                              moved between tasks
```

A **shuffle** writes data to disk and moves it between tasks, so it's usually the slowest part of a Spark job. A big part of this project's design is **avoiding giant shuffles** (Lesson 5).

## 4.5 MapReduce: the idea underneath

The classic big-data pattern has two phases:

```
   MAP     process each record or group independently (in parallel)
   REDUCE  combine results with an aggregation (sum, mean, count, percentile)
```

Example from the project — **mean heatwave days per year** ([pipeline/export_dashboard.py](pipeline/export_dashboard.py)):

```
   rows (cell, year, category)
      │ MAP:    is_hot = (category > 0)            for every row, in parallel
      ▼
   group by (cell, year) → REDUCE: sum(is_hot)    = heatwave days of that cell in that year
      ▼
   group by year         → REDUCE: mean            = average over all cells
      ▼
   one number per year, e.g. 2016: 75 … 2024: 133   (44 rows)
```

The **climatology** (Lesson 3) is also map-reduce: group by cell (and calendar day), reduce to a mean and a 90th percentile.

## 4.6 `applyInPandas`: the project's main trick

Some steps are easy in numpy but painful in SQL, e.g. the climatology with its 11-day window, or clustering a whole day's map. Spark offers:

```python
result = df.groupBy("cell_id").applyInPandas(my_function, schema="...")
```

```
   Spark table (billions of rows)
        │ groupBy("cell_id")
        ▼
   ┌──────────┐ ┌──────────┐ ┌──────────┐
   │ cell 1   │ │ cell 2   │ │ cell 3   │   each group arrives as a normal
   │ pandas DF│ │ pandas DF│ │ pandas DF│   pandas DataFrame (via Apache Arrow)
   └────┬─────┘ └────┬─────┘ └────┬─────┘
        ▼            ▼            ▼
    my_function  my_function  my_function     your numpy code, in parallel on all cores
        ▼            ▼            ▼
   └──────────── results combined into one Spark table ─────────────┘
```

Where the project uses it:

| Stage | Group by | Each group is | The function does |
|---|---|---|---|
| B | `cell_id` | one cell's 16,071 days | climatology + heatwave detection |
| C | `date` | one day's hot cells (a map) | grid DBSCAN clustering |
| E pass 1 | `cell_id` | one cell's whole history | time-series features |
| E pass 2 | `date` | one day's whole map | neighbourhood features |

So **Spark handles scale** (splitting, scheduling, reading, writing) and **numpy handles the science**. The numpy functions can be unit-tested without Spark ([tests/test_hobday.py](tests/test_hobday.py)).

ML analogy: like `Dataset.map(fn, num_parallel_calls=…)` — you write the per-example function, the framework parallelises it.

## 4.7 Window functions: "look at nearby rows"

A window function computes something over neighbouring rows of the same group, in order:

```python
w = Window.partitionBy("cell_id").orderBy("date")
df.withColumn("value_3_days_ago", F.lag("nb_exceed_7", 3).over(w))
```

| cell_id | date | nb_exceed_7 | lag 3 (3 days earlier) | trend = today − 3 days ago |
|---|---|---|---|---|
| 579170 | 1 May | 0.10 | – | – |
| 579170 | 2 May | 0.12 | – | – |
| 579170 | 3 May | 0.15 | – | – |
| 579170 | 4 May | 0.25 | 0.10 | +0.15 |
| 579170 | 5 May | 0.40 | 0.12 | +0.28 |

Used in [pipeline/features.py](pipeline/features.py) for `nb_exceed_trend_3`.

## 4.8 Why CPUs and not the DGX's GPUs?

The work is mostly **reading/writing files** and **per-cell time-series arithmetic**, not large matrix multiplications. CPUs do this well; GPUs would mostly wait for data. (GPU Spark exists, e.g. RAPIDS, but wasn't needed.)

## 4.9 Evidence of scale: the run log

Every stage appends rows, seconds and output size to `outputs/<mode>/tables/run_log.csv` ([hot_oceans/runlog.py](hot_oceans/runlog.py)):

```
   timestamp            stage step         rows        seconds  note
   2026-11-04T11:46:47  A     lake_check   937485714   48.4     duplicates=0 nulls=0
   2026-11-04T11:50:27  B     summary      937485714    4.2     heatwave cell-days=67168808 (7.2%)
   2026-11-04T11:50:51  C     dbscan        66466009   15.3
```

Full pipeline ≈ **81 minutes** on the DGX. Heatwave detection over all 937.5 M rows took only ≈ **3.3 minutes**.

## Summary of Lesson 4

- 937 M rows (~40 GB in memory) don't fit in pandas; Spark splits tables into **partitions** processed in parallel.
- **Lazy**: transformations build a plan; actions run it, optimised by Catalyst.
- **Shuffles** (moving rows to group them) are the expensive part.
- **MapReduce**: map per row/group, reduce with an aggregation.
- **applyInPandas**: each group (one cell, or one day) is processed by normal numpy code, in parallel.
- `local[N]` = one machine with N cores (8 on the PC, 48 on the DGX).

**Quick check**

1. Stage B groups by `cell_id`, Stage C by `date`. Why? *Answer: Stage B needs one cell's full time series (climatology); Stage C needs one day's full map (spatial clusters).*
2. `df.filter(...)` returns instantly even on a billion rows. Why? *Answer: it's a lazy transformation; nothing runs until an action.*

---

# Lesson 5: How the data is stored — Parquet and partitioning

## The lesson in one picture

```
   data/full/lake/sst_anom/                 ← one table = one folder
   ├── cell_bucket=0/   part-…parquet       ← one sub-folder per bucket
   ├── cell_bucket=1/   part-…parquet          (cell_id % 64)
   │   …
   ├── cell_bucket=34/  part-…parquet       ← Lakshadweep lives here (579170 % 64 = 34)
   │   …
   └── cell_bucket=63/  part-…parquet

   "give me Lakshadweep"  → Spark opens ONLY cell_bucket=34  (1/64 of the data)
```

## 5.1 CSV vs Parquet

**CSV** stores rows as text. **Parquet** stores columns, in binary, compressed.

```
   CSV (row by row, text)                 PARQUET (column by column, binary)
   cell_id,date,sst,category              cell_id : 579169 579170 578729 …
   579169,2023-05-01,29.1,0               date    : 2023-05-01 2023-05-01 …
   579170,2023-05-01,29.3,1               sst     : 29.1 29.3 29.0 …
   578729,2023-05-01,29.0,0               category: 0 1 0 …
```

Why Parquet is much faster for analytics:

| Feature | What it means | Example |
|---|---|---|
| **Columnar** | read only the columns you need (**column pruning**) | a query on `category` skips `sst`, `clim`, … |
| **Compressed** | similar values sit together and compress well | dates repeat, categories are mostly 0 |
| **Typed** | numbers stored as numbers, no text parsing | float32, date, tinyint |
| **Statistics** | each chunk stores min/max; chunks that can't match are skipped (**predicate pushdown**) | `date >= 2023-01-01` skips older chunks |

ML analogy: storing a dataset as sharded TFRecord/WebDataset files instead of one big CSV.

## 5.2 The data lake

Instead of a database, the big tables are **folders of Parquet files** — a **data lake** (`data/<mode>/lake/`):

```
   raw NetCDF (≈1.6 GB)
        │ Stage A
        ▼
   sst_by_year  ──►  sst_by_cell (≈1.7 GB)         clean SST, by bucket
                         │ Stage B
                         ▼
                     sst_anom (≈14 GB)              + clim, thresh, anomaly, ratio, category
                      │            │ Stage E
                      │            ▼
                      │        cell_features, nb_features, training_v2   (model tables)
                      │ Stage C
                      ▼
                  clusters (≈0.8 GB) → footprints (≈0.15 GB, GeoParquet) → events (≈1 MB)

   cells (≈4 MB, GeoParquet): one row per ocean cell with its point and square
```

The lake grows from 1.6 GB of raw files to about 26 GB, because each stage adds columns and tables.

## 5.3 Partitioning: one folder per key value

Spark can split a table into folders by a column's value ("Hive-style" partitioning):

```python
df.write.partitionBy("cell_bucket").parquet("lake/sst_anom")
```

Reading a single folder reads only that part (**partition pruning**):

```python
spark.read.parquet("lake/sst_anom/cell_bucket=34")     # 1/64 of the table
```

## 5.4 Buckets: `cell_bucket = cell_id % 64`

Every cell goes into one of **64 buckets**, by the remainder of its ID:

```
   cell_id   % 64   bucket
   579168    → 32
   579169    → 33
   579170    → 34     ← Lakshadweep
   579171    → 35
   …
```

Why the remainder (modulo)?

- **Even spread**: about 58,334 / 64 ≈ **911 cells per bucket**, so every bucket is a similar amount of work.
- Each bucket holds **all 44 years** of its cells — exactly what Stage B needs (one cell's full history).
- Neighbouring cells land in **different** buckets. That's fine: Stage B works per cell; steps that need a whole map (per day) read the whole table anyway.

## 5.5 Two layouts, and switching without a giant shuffle

```
   what the download gives:  BY YEAR                 what Stage B needs:  BY CELL
   oisst_1982 ─ all cells, 1982                      bucket 0  ─ its cells, all years
   oisst_1983 ─ all cells, 1983          ?           bucket 1  ─ its cells, all years
   …                                   ─────►        …
   oisst_2025 ─ all cells, 2025                      bucket 63 ─ its cells, all years
```

Re-organising 937 M rows at once would be one giant shuffle. Stage A does it **one year at a time**:

```
   for each year (44 times):
       read that year (~21 million rows)
       split its rows into the 64 buckets          ← a SMALL shuffle
       APPEND each piece to lake/sst_by_cell/cell_bucket=NN/

   after year 1:   bucket 34 = [1982]
   after year 2:   bucket 34 = [1982][1983]
   …
   after year 44:  bucket 34 = [1982][1983] … [2025]   ← all years of its cells
```

44 small shuffles instead of one huge one. Code: [pipeline/stage_a_ingest.py](pipeline/stage_a_ingest.py), lines with `.repartition(nb, "cell_bucket").write.mode("append").partitionBy("cell_bucket")`.

Stage B then runs **one bucket at a time** (`--buckets` lets you pick some), so even the DGX never holds the whole table at once.

## 5.6 Resumability (like training checkpoints)

Long jobs crash or get stopped. Each stage remembers what is finished:

```
   lake/_sst_by_cell_years_done.txt      Stage A: list of years already appended → skipped next time
   lake/sst_anom/cell_bucket=34/_SUCCESS Stage B: bucket 34 finished → skipped next time
   lake/training_v2/cell_bucket=34/_SUCCESS  Stage E: same idea
```

```
   run 1:  bucket 0 ✔  1 ✔  2 ✔ … 40 ✔  41 ✘ (crash)
   run 2:  bucket 0 skip … 40 skip, 41 ✔ … 63 ✔        ← continues where it stopped
```

`--force` ignores the markers and redoes everything. ML analogy: resuming training from the last checkpoint.

One trap (documented in the DGX notes): Stage A **appends**, so re-running it on top of an old lake would duplicate rows. That's why [dgx/redo_full.sh](dgx/redo_full.sh) deletes the old lake before rebuilding.

## 5.7 GeoParquet

**GeoParquet** = Parquet + a geometry column (stored as binary **WKB**, Lesson 6) + metadata saying which CRS (EPSG:4326). Used for `cells` and `footprints`, and as the stand-in for PostGIS tables in `outputs/<mode>/postgis/` (Lesson 7).

## Summary of Lesson 5

- **Parquet** = columnar, compressed, typed, with chunk statistics → reads only what's needed.
- The **data lake** is folders of Parquet files, not a database.
- **Partitioning** by `cell_bucket = cell_id % 64` → ~911 cells per bucket, all years together; read one bucket at a time.
- Stage A switches year-layout → cell-layout **one year at a time** to avoid a giant shuffle.
- `_SUCCESS` markers and a done-file make stages **resumable**.

**Quick check**

1. Which bucket holds cell 518,720? *Answer: 518,720 % 64 = 0 (518,720 = 64 × 8,105).*
2. Why not put neighbouring cells in the same bucket? *Answer: modulo spreads work evenly; Stage B works per cell, so neighbours don't need to be together.*

---

# Lesson 6: Spatial SQL with Apache Sedona

## The lesson in one picture

```
   Spark alone:      numbers, text, dates           ✗ no shapes
   Spark + Sedona:   + GEOMETRY type + ST_ functions + fast spatial joins

   Three jobs in this project:
   ① which sea region is each cell in?      ST_Contains   (point in polygon)      Stage A
   ② turn a blob of hot cells into a shape  ST_ConvexHull + ST_Buffer               Stage C
   ③ is today's shape overlapping yesterday's?  ST_Intersects (spatial self-join)  Stage C
```

## 6.1 Why Sedona

Spark knows numbers, strings and dates, but not **shapes**. **Apache Sedona** (formerly GeoSpark) adds:

- a **geometry** type (points, lines, polygons) inside Spark tables;
- 100+ spatial SQL functions named `ST_…` ("Spatial Type"), the same standard names used by PostGIS;
- fast **spatial joins** (joins whose condition is spatial), using spatial partitioning and indexes.

Version: Sedona 1.6.1 on Spark 3.5. It's switched on in [hot_oceans/spark.py](hot_oceans/spark.py) (`SedonaContext.create`). The **smoke test** ([pipeline/smoke_test.py](pipeline/smoke_test.py)) checks it works on a new machine: three points, one box around Lakshadweep, and `ST_Contains` must find that only point 1 is inside.

## 6.2 Writing shapes: WKT

**WKT (Well-Known Text)** is the readable text form of a geometry:

```
   POINT (72.625 10.625)

   LINESTRING (104 -10.5, 103 -11, 101 -12)

   POLYGON ((72.5 10.5, 72.75 10.5, 72.75 10.75, 72.5 10.75, 72.5 10.5))
```

```
   the polygon above (one 0.25° cell):

   (72.5,10.75) ┌──────────┐ (72.75,10.75)
                │    •     │   • = centre (72.625, 10.625)
   (72.5,10.5)  └──────────┘ (72.75,10.5)
                ↑ the ring ends where it started (first point repeated)
```

Two rules to remember:

- **x first, then y** → **longitude first, then latitude**. `POINT (72.6 10.6)`, not `(10.6 72.6)`.
- A polygon's outer ring **closes** by repeating the first point.

**WKB (Well-Known Binary)** is the compact binary version stored inside Parquet files.

## 6.3 Spatial predicates: yes/no questions about two shapes

```
 ST_Contains(A, B)     B completely inside A          ┌─────A─────┐
                                                      │   • B     │      TRUE
                                                      └───────────┘

 ST_Intersects(A, B)   A and B share any point        ┌──A──┐
                       (overlap or touch)             │   ┌─┼──B─┐     TRUE
                                                      └───┼─┘    │
                                                          └──────┘

                                                      ┌─A─┐   ┌─B─┐    FALSE
                                                      └───┘   └───┘    (gap between them)

 ST_DWithin(A, B, d)   A and B within distance d      •A ←─ d ─→ •B     TRUE if gap ≤ d
```

## 6.4 Functions that build shapes

| Function | What it does |
|---|---|
| `ST_Point(lon, lat)` | makes a point |
| `ST_PolygonFromEnvelope(xmin, ymin, xmax, ymax)` | makes a rectangle (each cell's square) |
| `ST_GeomFromWKT(text)` | text → geometry |
| `ST_Union_Aggr(geom)` | **aggregate**: merges many shapes into one (like `SUM` for shapes) |
| `ST_ConvexHull(geom)` | smallest convex shape around it (a rubber band) |
| `ST_Buffer(geom, d)` | grows the shape outward by distance d |
| `ST_AsText(geom)` | geometry → WKT text |

## 6.5 Job ① — which ecoregion is each cell in? (Stage A)

A **point-in-polygon join** between 58,334 cell centres and the MEOW ecoregion polygons ([pipeline/stage_a_ingest.py](pipeline/stage_a_ingest.py), `build_cells`):

```sql
WITH c AS (
  SELECT cell_id, lat, lon, area_km2, sector,
         ST_Point(lon, lat)                                         AS geometry,   -- centre point
         ST_PolygonFromEnvelope(lon-0.125, lat-0.125, lon+0.125, lat+0.125) AS cell_poly  -- the square
  FROM cells_raw)
SELECT c.*, m.ecoregion
FROM c LEFT JOIN meow m ON ST_Contains(m.geom, c.geometry)
```

Line by line:

1. Make each cell's **centre point** and its **0.25° square** (centre ± 0.125°).
2. Join each point with the ecoregion polygon that **contains** it.
3. `LEFT JOIN` keeps cells that are in **no** ecoregion (their `ecoregion` is empty).

```
   ┌──────── "Maldives" ────────┐
   │  •   •   •                  │   these cells get ecoregion = "Maldives"
   │  •   •   •                  │
   └──────────────────────────────┘
          •   •   •   •                 open-ocean cells: no ecoregion (NULL)
```

Result: 46 ecoregions touch the box; **29,236 cells (50.1%)** are inside one. MEOW only covers **coasts and shelf seas**, so the rest (open ocean) keep only their **sector** label: Arabian Sea, Bay of Bengal, Andaman/SCS edge, Equatorial, South-west, South-east ([hot_oceans/climate.py](hot_oceans/climate.py), `sector`).

## 6.6 Job ② — turning a blob of hot cells into a footprint polygon (Stage C)

For every day and every cluster of hot cells (clusters come from DBSCAN, Lesson 8):

```sql
SELECT date, cluster, count(*) AS n_cells, sum(area) AS area_km2, …,
       ST_Buffer(ST_ConvexHull(ST_Union_Aggr(ST_Point(lon, lat))), 0.2) AS geom
FROM cl GROUP BY date, cluster
HAVING count(*) >= 20
```

Step by step:

```
   1. points at hot cell centres     2. ST_Union_Aggr → one multi-point
      •  •  •                            (same dots, now one geometry)
      •  •  •  •
         •  •  •

   3. ST_ConvexHull (rubber band)    4. ST_Buffer 0.2° (grow outward)
      ┌────────┐                        ╭──────────╮
      │        └──┐                     │          ╰──╮
      └──┐        │                     ╰──╮          │
         └────────┘                        ╰──────────╯
```

- **Convex hull**: imagine stretching a rubber band around all the points; the shape it makes.
- **Buffer 0.2°** (≈ 22 km): makes the shape a little bigger so that blobs sitting **side by side** on consecutive days actually overlap (needed for Job ③).
- `HAVING count(*) >= 20`: only clusters of **20+ cells** become footprints (tiny blobs are ignored).

Result: **291,272** daily footprints (full run), saved as GeoParquet. This is the **raster → vector** step from Lesson 1. The same query also computes each footprint's area, strongest category, max and mean anomaly, and area-weighted centre.

## 6.7 Job ③ — linking footprints through time (Stage C)

A **spatial self-join**: compare each footprint on day *d* with each footprint on day *d + 1*:

```sql
SELECT a.date AS d1, a.cluster AS c1, b.date AS d2, b.cluster AS c2
FROM fp a JOIN fp b
  ON b.date = date_add(a.date, 1)        -- the next day
 AND ST_Intersects(a.geom, b.geom)       -- the shapes overlap
```

```
   day d:     ┌───A───┐                       ┌─C─┐
              └───────┘                       └───┘
   day d+1:        ┌────B────┐                          ┌─D─┐
                   └─────────┘                          └───┘
   A ∩ B overlap → link (A, B) = same heatwave continuing
   C, D no overlap → no link
```

Result: **322,279 links** (full run). Lesson 8 shows how links become events.

## 6.8 Why spatial joins need special handling

A naive join compares **every pair**: with 291,272 footprints that's ~85 billion exact geometry tests. Sedona avoids this:

```
   1. SPATIAL PARTITIONING   split the map into regions; only shapes in the same region are compared
      ┌────┬────┬────┐
      │ A  │    │  C │
      ├────┼────┼────┤
      │  B │    │    │
      └────┴────┴────┘

   2. SPATIAL INDEX (R-tree) a tree of bounding boxes, for fast "what is near here?" lookups

   3. FILTER and REFINE
      filter:  cheap test — do the bounding RECTANGLES overlap?    ┌──┐┌──┐  no → skip
      refine:  exact test only for candidates that passed          (real polygon geometry)
```

Here the condition `b.date = a.date + 1` also limits each footprint to the next day's footprints (about 18 per day on average).

ML analogy: like using an approximate-nearest-neighbour index (e.g. FAISS) instead of comparing every pair of embeddings.

## 6.9 A note on units

Coordinates are in **degrees** (EPSG:4326), so `ST_Buffer(geom, 0.2)` grows by 0.2° (≈ 22 km at the equator, a bit less east–west at 30°). For distances in **metres**, PostGIS uses the `geography` type (Lesson 7).

## Summary of Lesson 6

- Sedona = Spark + geometry type + `ST_` functions + fast spatial joins.
- WKT is the text form; **longitude comes first**; polygons close on themselves.
- Predicates: **Contains** (inside), **Intersects** (share any point), **DWithin** (near).
- ① **point-in-polygon** cells → ecoregions (50.1% covered); ② **union → convex hull → buffer** = footprints (291,272); ③ **ST_Intersects** self-join of consecutive days = links (322,279).
- Spatial joins are fast thanks to spatial partitioning, R-tree indexes and filter-and-refine.

**Quick check**

1. Why buffer the convex hull by 0.2° before linking? *Answer: so blobs that sit side by side on consecutive days actually overlap and get linked.*
2. Is `POINT (10.6 72.6)` Lakshadweep? *Answer: no — x is longitude, so that point is at 72.6°N, 10.6°E (in the Arctic). Lakshadweep is `POINT (72.6 10.6)`.*

---

# Lesson 7: Spatial databases (PostGIS)

## The lesson in one picture

```
   "Process big, serve small"

   ┌──────────────────────────────┐        ┌──────────────────────────────┐
   │  SPARK + SEDONA  (DGX)        │        │  POSTGIS  (PC)                │
   │  937 M rows, batch jobs       │  ───►  │  small result tables          │ ───► dashboard, QGIS,
   │  minutes per stage            │ copy   │  cells 58k · footprints 291k  │      SQL queries
   │                               │        │  events 14k · regimes 14k     │      (milliseconds)
   └──────────────────────────────┘        └──────────────────────────────┘
```

## 7.1 What PostGIS is

- **PostgreSQL**: a popular open-source relational database (tables, SQL, indexes).
- **PostGIS**: an extension that adds geometry types, the same `ST_` functions as Sedona, and **spatial indexes**.

GIS software (QGIS, web maps, dashboards) usually connects to PostGIS.

## 7.2 Why not put everything in PostGIS?

| | Spark + Sedona | PostGIS |
|---|---|---|
| Good at | huge batch processing, many cores | fast interactive queries on moderate tables |
| Data size here | 937 M rows | thousands to hundreds of thousands of rows |
| Used for | Stages A–E | serving results |

A single database server would be slow for billion-row batch jobs. So only the small **derived** tables go into PostGIS:

| Table | Rows (full run) | Written by | Geometry |
|---|---|---|---|
| `cells` | 58,334 | Stage A | each cell's 0.25° square |
| `mhw_footprints` | 291,272 | Stage C | daily heatwave polygons |
| `mhw_events` | 14,472 | Stage C | each event's peak-day footprint |
| `event_regimes` | 14,472 | Stage D | none (plain table) |

## 7.3 Spatial index: GiST

A normal index (B-tree) sorts values, like a phone book. Shapes can't be sorted in one line. **GiST** builds a tree of **bounding boxes** (like an R-tree):

```
                       ┌──────────── whole map ────────────┐
                       │                                    │
              ┌────────┴────────┐                 ┌─────────┴────────┐
              │  west half box   │                 │  east half box    │
              └───┬─────────┬───┘                 └───┬──────────┬────┘
               ┌──┴──┐   ┌──┴──┐                   ┌──┴──┐    ┌──┴──┐
               │ A B │   │ C D │                   │ E F │    │ G H │   ← the actual shapes
               └─────┘   └─────┘                   └─────┘    └─────┘

   Query: "what intersects this small area in the east?"
   → skip the whole west half immediately → only check E F G H
```

```sql
CREATE INDEX mhw_events_geom_gix ON mhw_events USING GIST (geometry);
```

ML analogy: like a KD-tree or ANN index for nearest-neighbour search — skip most of the data without checking it.

## 7.4 The example queries ([sql/schema.sql](sql/schema.sql))

**Query 1 — which ecoregions were touched by heatwave footprints in April–May 2024?**

```sql
SELECT c.ecoregion, count(DISTINCT f.event) AS events,
       round(sum(f.area_km2)::numeric) AS footprint_km2_days
FROM mhw_footprints f JOIN cells c ON ST_Intersects(f.geometry, c.geometry)
WHERE f.date BETWEEN '2024-04-01' AND '2024-05-31'
GROUP BY c.ecoregion ORDER BY footprint_km2_days DESC;
```

- Join daily footprints with cells where the shapes **intersect** (a spatial join, using GiST).
- Keep April–May 2024; group by ecoregion; count distinct events and add up area × days.

**Query 2 — longest events whose peak footprint is within 300 km of Lakshadweep**

```sql
SELECT event_id, start, duration_days, max_category
FROM mhw_events
WHERE ST_DWithin(geometry::geography,
                 ST_SetSRID(ST_MakePoint(72.64, 10.57), 4326)::geography,
                 300000)                       -- 300,000 metres
ORDER BY duration_days DESC LIMIT 10;
```

- `ST_MakePoint(72.64, 10.57)`: Lakshadweep (longitude first!); `ST_SetSRID(…, 4326)` says it's lat/lon.
- `::geography`: treat coordinates on the **curved Earth**, so distances are in **metres**, not degrees.

```
   geometry  → flat, units = degrees     (1° east-west ≠ same km everywhere)
   geography → round Earth, units = metres  ✓ correct for "within 300 km"
```

**Query 3 — regime mix by Indian Ocean Dipole phase**

```sql
SELECT iod_phase, regime, count(*) AS n
FROM event_regimes GROUP BY iod_phase, regime ORDER BY iod_phase, regime;
```

A plain SQL `GROUP BY` (no geometry needed).

## 7.5 How tables get into PostGIS

```
   Stage A/C/D ──► hot_oceans/db.py
                       │
         postgis.enabled = true?  ── yes ──► write straight into PostGIS + GiST index
                       │
                       no
                       ▼
            outputs/<mode>/postgis/<table>.parquet  (GeoParquet fallback)
                       │  copied to the PC
                       ▼
            python -m pipeline.load_postgis --env pc --mode full
                       ▼
            PostGIS on the PC (PostgreSQL 13 + PostGIS 3.4) + indexes from sql/schema.sql
```

- [hot_oceans/db.py](hot_oceans/db.py): `write_gdf` writes a spatial table and adds a GiST index, or saves GeoParquet if PostGIS is off.
- [pipeline/load_postgis.py](pipeline/load_postgis.py): loads every Parquet file from `outputs/<mode>/postgis/` into PostGIS, then runs the `CREATE INDEX` lines from `schema.sql`. The password can come from the `HOT_OCEANS_PG_DSN` environment variable, so it's never written in a file.

**Honest status** (checked 11 Nov 2026): in [config.yaml](config.yaml) `postgis.enabled` is **false**, so the DGX run saved the tables as GeoParquet. On the PC, `load_postgis.py` then loaded the full-basin tables into the project's private database: [sql/pg_local.ps1](sql/pg_local.ps1), port 5433, data in `data/pgdata`.

| Table | Rows in PostGIS | Rows in the GeoParquet file |
|---|---|---|
| cells | 58,334 | 58,334 |
| mhw_events | 14,472 | 14,472 |
| mhw_footprints | 291,272 | 291,272 |
| event_regimes | 14,472 | 14,472 |

- All geometry columns are polygons in SRID 4326, each with a GiST index. There are also indexes on `cell_id`, `start` and `date`.
- Query 2 in `schema.sql` (events within 300 km of Lakshadweep) runs in about 1 s.
- Query 1 (the footprint × cell join for April–May 2024: 25 events, 45 ecoregions) runs in about 2 s.
- **The dashboard does not read from PostGIS.** It reads the small files written by `export_dashboard.py` (Parquet/CSV/GeoJSON). This was a deliberate choice: the dashboard runs with no database server. PostGIS is the place for spatial SQL queries, and for GIS tools such as QGIS.
- To use it after a PC restart, run `powershell -ExecutionPolicy Bypass -File sql\pg_local.ps1 start`, then `... pg_local.ps1 psql`.

## Summary of Lesson 7

- PostGIS = PostgreSQL + spatial types + `ST_` functions + **GiST** indexes.
- **Process big (Spark), serve small (PostGIS)**: only cells, footprints, events and regimes go in.
- GiST = a tree of bounding boxes that skips far-away shapes.
- `::geography` gives distances in metres on the round Earth.
- The DGX run saved GeoParquet, and `load_postgis.py` loaded it into PostGIS on the PC: all 4 tables, with row counts matching the files. The dashboard reads files, not PostGIS.

**Quick check**

1. Why not load all 937 M rows into PostGIS? *Answer: one database server is slow for billion-row batch processing; Spark parallelises it. Queries and the dashboard only need the small derived tables.*
2. Why `::geography` in query 2? *Answer: so the 300 km distance is measured in metres on the Earth's surface, not in degrees.*

---

# Lesson 8: Clustering in space — DBSCAN and tracking heatwaves

## The lesson in one picture

```
   DAY 1                 DAY 2                 DAY 3
   hot cells             hot cells             hot cells
   . # # . .             . . # # .             . . . # #
   . # # # .             . . # # #             . . . # #
   . . # . .             . . . # .             . . . . #
       │ DBSCAN               │ DBSCAN               │ DBSCAN          ← cluster each day
       ▼                      ▼                      ▼
   footprint A1  ──overlap──► footprint A2 ──overlap──► footprint A3   ← link consecutive days
       └───────────────── one EVENT, moving east ─────────────────┘   ← union-find
```

ML/DL analogy: **multi-object tracking in video**. Detect objects in each frame, then associate detections across frames by overlap (like IoU matching). Each day is a frame; each blob of hot cells is a detected object.

## 8.1 Why events?

After Stage B every cell-day has a category, but that's 67 million separate hot cell-days. Scientists want **events**: "a heatwave covering the Arabian Sea from 3 March to 20 April that grew and moved east". That needs two steps:

1. **Each day**: group neighbouring hot cells into blobs (clustering).
2. **Across days**: connect blobs that continue from one day to the next (tracking).

## 8.2 DBSCAN recap

**DBSCAN** (Density-Based Spatial Clustering of Applications with Noise) has two settings:

- `eps`: how close two points must be to count as neighbours.
- `min_samples`: how many points within `eps` (counting itself) make a point a **core** point.

Three kinds of point:

```
   CORE    has ≥ min_samples points within eps         → forms the cluster's body
   BORDER  not core, but within eps of a core point    → joins that cluster
   NOISE   neither                                      → label −1 (ignored)
```

Why DBSCAN and not K-Means here?

- No need to choose the number of clusters (the number of blobs changes every day).
- Finds **any shape** (heatwave blobs are irregular).
- Ignores isolated hot cells as **noise**.

## 8.3 DBSCAN on a grid: the project's own exact version

Settings ([config.yaml](config.yaml), `events:`): `eps = 1.5` cells, `min_samples = 4`, measured on **row/column indices**, not degrees.

On a square grid, distance ≤ 1.5 means **exactly the 8 surrounding cells**:

```
   distance from the centre cell X:

   1.41  1.0  1.41          side neighbours:     1.0   ≤ 1.5 ✓
   1.0    X   1.0           diagonal neighbours: 1.41  ≤ 1.5 ✓
   1.41  1.0  1.41          next ring out:       2.0   > 1.5 ✗
```

So DBSCAN becomes simple **image operations** ([hot_oceans/events.py](hot_oceans/events.py), `cluster_day`):

### Worked example

**Step 1 — the hot cells of one day** (`#` = in a heatwave):

```
        c0 c1 c2 c3 c4 c5 c6
   r0    .  .  .  .  .  .  .
   r1    .  #  #  #  .  .  .
   r2    .  #  #  #  .  .  #
   r3    .  .  #  .  #  .  .
   r4    .  .  .  .  .  .  .
```

**Step 2 — count hot cells in each 3×3 window** (a convolution with a 3×3 kernel of ones, exactly like a CNN filter). Counts for the hot cells only:

```
        c0 c1 c2 c3 c4 c5 c6
   r1    .  4  6  4  .  .  .
   r2    .  5  7  6  .  .  1
   r3    .  .  4  .  2  .  .
```

e.g. cell (r2,c2): its 3×3 window holds (1,1),(1,2),(1,3),(2,1),(2,2),(2,3),(3,2) = 7 hot cells.

**Step 3 — core cells** = hot cells with count ≥ 4:

```
        c0 c1 c2 c3 c4 c5 c6
   r1    .  C  C  C  .  .  .
   r2    .  C  C  C  .  .  ·      (2,6): count 1 → not core
   r3    .  .  C  .  ·  .  .      (3,4): count 2 → not core
```

**Step 4 — connected components of the core cells** (`scipy.ndimage.label` with 8-connectivity) → all 7 core cells touch → **cluster 0**.

**Step 5 — border and noise:**

- (3,4): not core, but touches core cell (2,3) diagonally → **border** → joins cluster 0.
- (2,6): not core, touches no core cell → **noise** (−1).

```
   final labels:
        c0 c1 c2 c3 c4 c5 c6
   r1    .  0  0  0  .  .  .
   r2    .  0  0  0  .  . -1
   r3    .  .  0  .  0  .  .
```

This gives **exactly** the DBSCAN result (a unit test checks core, border and noise: `test_grid_dbscan_core_border_noise`), but much faster than general DBSCAN, and it avoided a scikit-learn crash on Windows.

It runs once per day with `groupBy("date").applyInPandas` (Lesson 4), so all 16,071 days are clustered in parallel. Full run: **66.5 million** hot cell-days clustered in about **15 seconds** on the DGX.

## 8.4 From clusters to footprints and links

- Each cluster with **≥ 20 cells** becomes a **footprint polygon** with Sedona (Lesson 6, Job ②): **291,272** footprints.
- Footprints on consecutive days that **intersect** are linked (Lesson 6, Job ③): **322,279** links.

## 8.5 Union-find: turning links into events

Think of a **graph**: each footprint is a node, each link is an edge. An **event** is a **connected component** — everything reachable through links.

```
   day 1      day 2      day 3

    A1 ─────── A2 ─────── A3
                         ╱
              B2 ───────╱            B2 also overlaps A3 → the two blobs MERGE

    C1                               C1 has no link → its own component (and dropped if < 5 days)

   components:  {A1, A2, A3, B2}   {C1}
```

**Union-find** (also called disjoint-set) finds connected components efficiently:

```
   start:            each node is its own group   A1  A2  A3  B2  C1
   union(A1, A2):    A1 ← A2                       {A1,A2}  A3  B2  C1
   union(A2, A3):    … ← A3                        {A1,A2,A3}  B2  C1
   union(B2, A3):    … ← B2                        {A1,A2,A3,B2}  C1
   find(B2) → A1     "which group is B2 in?" → the group whose representative is A1
```

- `union(a, b)`: merge the groups of a and b.
- `find(x)`: return the representative of x's group; **path compression** makes later lookups faster by pointing nodes straight at the representative.

With ~300 k edges this runs on the driver in plain Python ([hot_oceans/events.py](hot_oceans/events.py), `UnionFind` and `link`). Components lasting **≥ 5 days** become events (`min_event_days` in config).

## 8.6 The event catalogue

[pipeline/stage_c_events.py](pipeline/stage_c_events.py), `build_catalogue`, turns each component into one row:

| Property | Meaning |
|---|---|
| `event_id` | e.g. `E-2022-199` = the 199th event that started in 2022 |
| `start`, `end`, `duration_days` | when |
| `peak_area_km2` | largest daily area (real cell areas, corrected for latitude) |
| `max_intensity`, `mean_intensity` | largest / average anomaly (°C) |
| `cum_intensity` | daily average anomaly summed over all days (°C·days) = total heat stress |
| `max_category` | worst Hobday category reached |
| `clat`, `clon` | area-weighted centre |
| track | line through the daily centres (LineString) |
| geometry | the footprint polygon on the peak day |

```
   example: E-2022-199 (south-eastern Indian Ocean)

   2 Nov 2022  starts near 10.5°S, 104°E
               grows to ≈121,000 km², max anomaly +1.7 °C
               centre drifts south-west for 37 days (moves 6.3°)
   8 Dec 2022  ends

        •───•───•───•───•          ← track of the daily centre (moving south-west)
                         ↘
```

Full-run catalogue: **14,472 events**. Median duration 7 days; 74% last ≤ 10 days; 560 last ≥ 30 days; 55 last ≥ 100 days. By peak category: 7,682 Moderate, 5,932 Strong, 768 Severe, 90 Extreme.

## 8.7 Weakness: chaining

The rule "any overlap on consecutive days = same event" can chain many patches into one giant event:

```
   day 1   ▓▓               day 2    ▓▓▓▓        day 3        ▓▓▓▓▓▓▓
           (Arabian Sea)              touches the next patch…      … and the next …
   → after months, patches across the whole basin are ONE "event"
```

With the fixed baseline in a warming ocean (Lesson 3.7), recent years produce multi-year, basin-wide "events": **E-2014-009** lasts **1,056 days** (2014–2016), **E-2023-028** was still active at the end of the record (31 Dec 2025).

Possible fixes (future work):

- require a **minimum overlap fraction** (like an IoU threshold in object tracking) instead of "any overlap";
- **concave hulls** instead of convex hulls (convex hulls of big patches can cover land);
- a **detrended baseline**.

## Summary of Lesson 8

- Events = **cluster each day** (DBSCAN) → **footprints** (Sedona) → **link** consecutive days (ST_Intersects) → **connected components** (union-find).
- Grid DBSCAN with eps 1.5 = 3×3 convolution count → core cells → connected components → border/noise: exact and fast.
- Like video object tracking: detect per frame, associate by overlap.
- 14,472 events; most are short, but chaining makes some unrealistically long.

**Quick check**

1. In the worked example, if `min_samples` were 5, would (1,1) be core? *Answer: no — its count is 4.*
2. Day 1 has blobs A and B; on day 2 one blob C overlaps both. How many events? *Answer: one — A–C and B–C links put A, B and C in the same connected component (a merge).*

---

# Lesson 9: K-Means regimes and association rules (FP-Growth)

Both run in Stage D ([pipeline/stage_d_regimes_rules.py](pipeline/stage_d_regimes_rules.py)) on the **14,472 events** (one row per event, from Lesson 8), using Spark MLlib.

## The lesson in one picture

```
   14,472 events
        │
        ├── K-MEANS ──► "are there TYPES of heatwaves?"
        │                 → 3 regimes: short-intense · long-large · short-mild   (weakly separated)
        │                 → do the types change with El Niño / IOD?  (only a little)
        │
        └── FP-GROWTH ─► "IF region/season/climate … THEN severity/duration …?"
                          → 59 rules, all "→ Moderate", best lift 1.21   (weak)
```

## 9.1 K-Means: are there types of heatwaves?

### The features (9 per event)

| Feature | Why this form |
|---|---|
| log(duration) | durations are very skewed (most 5–10 days, a few 1,000) → log makes them comparable |
| log(peak area) | same reason |
| max intensity, mean intensity | how hot (°C anomaly) |
| log(1 + cumulative intensity) | total heat stress, skewed |
| centre latitude, centre longitude | where |
| sin(2π·month/12), cos(2π·month/12) | month is **cyclic**: December is next to January |

Why sin/cos for the month:

```
   month as a number:   Dec = 12, Jan = 1   → "far apart" (11)  ✗ wrong
   month on a circle:            Jan
                          Dec  •     •  Feb
                       Nov •           • Mar        Dec and Jan are neighbours ✓
                          …             …
   (sin, cos) gives each month a point on this circle
```

All features are **standardised** (mean 0, standard deviation 1), because K-Means uses distances; otherwise area (hundreds of thousands) would swamp intensity (a few °C).

### K-Means recap

```
   1. pick k random centres         2. assign each event to the nearest centre
   3. move each centre to the mean of its events     4. repeat 2–3 until stable
```

### Choosing k with the silhouette score

For each point:

```
   a = average distance to points in its OWN cluster
   b = average distance to points in the NEAREST OTHER cluster
   silhouette = (b − a) / max(a, b)          between −1 and +1

   example: a = 1, b = 3  →  (3 − 1) / 3 = 0.67   (well separated)
            a = 2, b = 2.2 → (2.2 − 2) / 2.2 = 0.09 (overlapping)
```

```
   high silhouette (≈ 0.7)            low silhouette (≈ 0.25)
     ●●●          ○○○                    ●●●○●○○●○○
     ●●●          ○○○                    ○●●●○○●○○○
   clear groups                         groups blur into each other
```

The project tries k = 3 … 8 and keeps the best silhouette (full run, `outputs/full/tables/kmeans_selection.csv`):

| k | silhouette |
|---|---|
| **3** | **0.262** ← best |
| 4 | 0.236 |
| 5 | 0.229 |
| 6 | 0.232 |
| 7 | 0.230 |
| 8 | 0.230 |

0.26 means the regimes **overlap a lot**: event properties form a continuum rather than clear types.

### The three regimes

| Regime | Events | Mean duration | Mean peak area | Mean max anomaly | Name |
|---|---|---|---|---|---|
| 0 | 4,273 | 7.6 days | 43,900 km² | 2.13 °C | short, intense |
| 1 | 2,534 | 28.0 days | 381,900 km² | 2.41 °C | long, large |
| 2 | 7,665 | 6.9 days | 38,600 km² | 1.47 °C | short, mild |

### Do the regimes depend on El Niño or the IOD?

Each event gets the IOD and ENSO phase of its start month (DMI ≥ +0.4 = IOD+, ≤ −0.4 = IOD−; ONI ≥ +0.5 = El Niño, ≤ −0.5 = La Niña; Lesson 3.8). Then a cross-table of shares:

| IOD phase | short-intense | long-large | short-mild |
|---|---|---|---|
| IOD+ | 25.7% | **18.6%** | 55.7% |
| IOD neutral | 29.4% | 17.6% | 53.1% |
| IOD− | 33.7% | **16.3%** | 50.0% |

Long-large events are only slightly more common in positive-IOD months. The differences are small; also 78% of events start in IOD-neutral months, so the IOD+ and IOD− groups are small. Honest conclusion: **monthly climate phases explain little about daily event types.**

## 9.2 FP-Growth: association rules

### The idea: market-basket analysis

Supermarkets ask: "people who buy bread and butter also buy … milk?" Here each **event** is a "basket" of items ([stage_d_regimes_rules.py](pipeline/stage_d_regimes_rules.py)):

```
   an event:        { sector=Arabian Sea, season=MAM, iod=IOD0, enso=ElNino, cat=Strong, short<30d }
   another event:   { sector=South-east,  season=MAM, iod=IOD0, enso=ElNino, cat=Moderate, short<30d }
   …  (illustrative baskets)
```

Item types: `sector` (6 regions), `season` (DJF, MAM, JJA, SON), `iod` (IOD+, IOD0, IOD−), `enso` (ElNino, ENSO0, LaNina), `cat` (Moderate, Strong, Severe+), duration (`long>=30d` or `short<30d`).

A rule looks like `{A, B} ⇒ {C}`: "if an event has A and B, it tends to have C". Only rules whose result (C) is about **severity or duration** are kept.

### Support, confidence, lift — a toy example with 10 events

```
   event:   1  2  3  4  5  6  7  8  9  10
   SE+short ✓  ✓  ✓  ✓  ✓  .  .  .  .  .     (5 events are South-east AND short)
   Moderate ✓  ✓  ✓  ✓  .  ✓  .  .  .  .     (5 events are Moderate in total)
   both     ✓  ✓  ✓  ✓  .  .  .  .  .  .     (4 events have all three)
```

Rule: `{sector=South-east, short<30d} ⇒ {cat=Moderate}`

| Measure | Formula | Toy value | Meaning |
|---|---|---|---|
| **Support** | events with A, B and C ÷ all events | 4 / 10 = **0.40** | how common the whole pattern is |
| **Confidence** | events with A, B and C ÷ events with A and B | 4 / 5 = **0.80** | P(C given A and B): how reliable |
| **Lift** | confidence ÷ P(C) | 0.80 / 0.50 = **1.6** | how much more likely C is, compared with chance |

```
   lift = 1    → A, B tell you NOTHING about C (independent)
   lift > 1    → C is more likely when A, B hold
   lift < 1    → C is less likely when A, B hold
```

Confidence alone can mislead: if 90% of all events are Moderate, a rule with confidence 0.9 adds nothing (lift 1.0).

### Why FP-Growth?

The older **Apriori** algorithm generates and counts every candidate item combination, which explodes with many items. **FP-Growth** compresses all baskets into a tree of shared prefixes (an **FP-tree**) and mines frequent combinations from it, with no candidate generation:

```
   baskets  {a,b,c} {a,b} {a,c} {a,b,c}          FP-tree (shared prefixes counted once)
                                                   root
                                                    └ a:4
                                                       ├ b:3
                                                       │  └ c:2
                                                       └ c:1
```

Settings: minimum support 0.05 (pattern in ≥ 5% of events), minimum confidence 0.5.

### Results (full run, `outputs/full/tables/rules.csv`)

| If (antecedent) | Then | Confidence | Lift | Support |
|---|---|---|---|---|
| South-east, ENSO neutral, IOD neutral, short | Moderate | 0.644 | 1.214 | 0.058 |
| South-east, ENSO neutral, short | Moderate | 0.643 | 1.211 | 0.074 |
| South-west, ENSO neutral, short | Moderate | 0.638 | 1.203 | 0.063 |
| South-east, IOD neutral, short | Moderate | 0.636 | 1.198 | 0.118 |
| South-east, short | Moderate | 0.627 | 1.182 | 0.152 |
| IOD positive, short | Moderate | 0.614 | 1.157 | 0.059 |

- **59 rules**, all predicting **Moderate**; no rule predicting long or stronger events reached confidence 0.5.
- Best lift **1.21**: short southern events in neutral climate conditions are Moderate 64% of the time vs 53% overall.
- Honest conclusion: **real but weak** associations; season, sector and climate phase say little about how strong an event becomes. This matches the weak K-Means separation.

## Summary of Lesson 9

- **K-Means** on 9 standardised event features (logs for skewed values, sin/cos for month); k chosen by **silhouette** → k = 3, silhouette 0.26 = weak types.
- Regime shares change only a little with IOD/ENSO phase.
- **FP-Growth** rules: **support** (how common), **confidence** (how reliable), **lift** (vs chance; 1 = nothing).
- 59 rules, best lift 1.21 → weak; reported honestly.

**Quick check**

1. A rule has confidence 0.9 but lift 1.0. Useful? *Answer: no — the result happens 90% of the time anyway; the "if" part adds nothing.*
2. Why sin/cos for month instead of 1–12? *Answer: months are cyclic; with sin/cos, December and January are close, as they should be.*

---

# Lesson 10: The prediction model, and why evaluating spatial ML is tricky

Code: [pipeline/features.py](pipeline/features.py) and [pipeline/stage_e_model.py](pipeline/stage_e_model.py). This describes the model as **rebuilt on 8 Nov 2026** (after a leak was found, 10.2).

## The lesson in one picture

```
   TODAY (day t) for one cell                         NEXT 7 DAYS
   ─────────────────────────────                      ────────────
   not in a confirmed heatwave?  ── no ──► skip row
           │ yes
           ▼
   23 features, using ONLY data up to day t   ──►  model  ──►  P( in a heatwave on any of t+1 … t+7 )
   (own history + surrounding water)                              │
                                                                  ▼
                                                     score ≥ threshold → WARNING
```

## 10.1 The task, precisely

> For each cell-day that is **not already in a confirmed heatwave**, will the cell be **in a heatwave on any of the next 7 days**?

- **Binary classification**, one row per cell-day.
- **Confirmed heatwave** = SST already above the threshold for **5 or more days in a row, up to today**. You can know this on the day.
- **Label** = 1 if the heatwave flag (Lesson 3) is on for any day from t+1 to t+7, else 0.

```
   day:      t-2  t-1   t  │ t+1  t+2  t+3  t+4  t+5  t+6  t+7
   in MHW?    0    0    0  │  0    0    1    1    1    1    1     → label = 1 (heatwave within 7 days)
   in MHW?    0    0    0  │  0    0    0    0    0    0    0     → label = 0
             └── features use ──┘ └────────── label uses ──────────┘
                 only this side         only this side (the future)
```

The hindsight heatwave flag is allowed **only in the label**: the label is the future by definition.

## 10.2 The old model and its leak (important viva story)

The first version (used in the current report) had **look-ahead leakage**: it used information that wouldn't exist on day t.

Remember from Lesson 3.6: a day is flagged as a heatwave only once the hot spell reaches **5 days**. So the flag on day t can depend on days t+1 … t+4.

```
   above threshold?   ✔    ✔    ✔    ✔    ✔        (a spell starting on day t)
   day:               t   t+1  t+2  t+3  t+4
   heatwave flag on day t = 1   ← but you only KNOW this on day t+4
```

Where the old model used it:

| Old ingredient | Problem |
|---|---|
| rows = days with `category == 0` | choosing rows with the flag needs the future (days t+1…t+4) |
| `nb_mhw_frac` = share of neighbours "in a heatwave" | a neighbour flagged on day 1 of its spell reveals the spell will last 5 days |
| `mhw_days_90` = heatwave days in the last 90 | same flag |
| `dmi`, `oni` for the current month | published only after the month ends |

ML analogy: classic **target leakage** — like predicting loan default with a feature computed after the loan ended.

**How it was found:** [experiments/model_lab.py](experiments/model_lab.py) rebuilt the dev box as numpy arrays and compared setups with a fast scikit-learn gradient-boosting model:

| Setup (dev box, test 2019–2025) | Average precision |
|---|---|
| persistence rule ("hot today") on the old rows | 0.243 |
| old features, hindsight version (E0) | 0.230 |
| old features made real-time (E1) | **0.185** ← below persistence |

Once the leak was removed, the old feature set did **worse than the simple persistence rule**. So the old "beats persistence" result was partly leakage. Stage E was redesigned.

## 10.3 The new features (23, all known on day t)

### Pass 1 — the cell's own history (`groupBy("cell_id")`, Lesson 4)

| Feature | Meaning |
|---|---|
| `ratio` | today's intensity ratio (Lesson 3.5): how many "gaps" above normal |
| `ratio_7`, `ratio_30` | average ratio over the last 7 / 30 days |
| `ratio_trend_3` | ratio today − ratio 3 days ago |
| `trend_1`, `trend_3`, `trend_7` | anomaly today − anomaly 1 / 3 / 7 days ago |
| `run_len` | days in a row above the threshold, ending today |
| `days_since_exceed` | days since the cell was last above the threshold |
| `exceed_days_30` | days above the threshold in the last 30 |
| `ratio_max_7` | highest ratio in the last 7 days |
| `gap_to_thr_ahead` | (lowest threshold of the next 7 days) − today's SST = warming still needed |
| `thr_tend_7`, `clim_tend_7` | how the threshold / climatology changes over the next 7 days |

Example for one cell:

```
   day          t-4   t-3   t-2   t-1    t
   SST > thr?    ✘     ✘     ✔     ✔     ✔      run_len(t) = 3, days_since_exceed(t) = 0
```

**Is `gap_to_thr_ahead` leakage?** No. It looks at next week's **threshold**, which comes from the fixed 1991–2020 climatology — known years in advance, like knowing next week's dates. It uses no future SST.

```
   °C
   29.9 |                    _ _ _ _   next week's threshold (known in advance)
   29.6 | today's SST ●
          gap_to_thr_ahead = 29.9 − 29.6 = 0.3 °C still needed to cross
```

### Pass 2 — the surrounding water (`groupBy("date")`, image filters on each day's map)

| Feature | Window | Meaning |
|---|---|---|
| `nb_ratio` | 8 neighbours | average ratio of the surrounding cells |
| `nb_ratio_7` | 7×7 cells (~175 km) | average ratio nearby |
| `nb_ratio_21` | 21×21 cells (~525 km) | average ratio in the wider region |
| `nb_ratio_max_7` | 7×7 | hottest ratio nearby |
| `nb_exceed` | 8 neighbours | share of neighbours above the threshold |
| `nb_exceed_7`, `nb_exceed_21` | 7×7, 21×21 | share above the threshold nearby / regionally |
| `nb_confirmed` | 8 neighbours | share of neighbours in a confirmed heatwave |
| `nb_exceed_trend_3` | 7×7 | change of `nb_exceed_7` over 3 days (a window function) |

```
   8 neighbours (ring)        7×7 window                  21×21 window
   ┌─┬─┬─┐                    ┌───────────────┐           ┌─────────────────────────┐
   ├─┼─┼─┤                    │               │           │                         │
   ├─┼X┼─┤                    │       X       │           │            X            │
   ├─┼─┼─┤                    │               │           │                         │
   └─┴─┴─┘                    └───────────────┘           │                         │
   "next door"                "nearby"  ~175 km           └─────────────────────────┘
                                                           "the region"  ~525 km
```

ML analogy: the same idea as **receptive fields of different sizes** in a CNN. Computed with `scipy.ndimage` convolution / box filters on each day's map ([features.py](pipeline/features.py), `neighbours_for_day`).

### Deliberately left out

- **Latitude, longitude, season**: the model would memorise *places and seasons* instead of learning physics, and transfer badly to new regions.
- **DMI, ONI**: monthly and published late (leak), and they added little.
- The ratio features are already normalised per cell and date (Lesson 3), so they mean the same everywhere.

### The leakage audit

[experiments/leakage_audit.py](experiments/leakage_audit.py) takes 6,000 random cell-days, **cuts off all data after the forecast day**, recomputes the inputs from that truncated data, and compares with the stored features:

```
   checked 6,000 cell-days × 16 inputs → 0 mismatches     (experiments/results/leakage_audit.txt)
```

If any input secretly used future data, the truncated recomputation would differ.

## 10.4 Splitting by time: fit / validation / test

```
   1982 ─────────────────────── 2014 │ 2015 ── 2018 │ 2019 ──────── 2025
   │            FIT (train)          │  VALIDATION   │      TEST          │
   │      the models learn here      │ early stopping│ only for the final │
   │                                 │ threshold     │ reported scores    │
   │                                 │ model choice  │ (never for choices)│
```

Why by **time** and not a random split? Consecutive days of a cell are almost identical (**temporal autocorrelation**):

```
   random split:   day 100 → train,  day 101 → test,  day 102 → train
                   the test day is almost a copy of two training days → scores look too good
   time split:     train on the past, test on the future → like real forecasting
```

## 10.5 Thinning and weights

The fit years have tens of millions of rows (hundreds of millions in the full basin), mostly negatives. To keep training manageable, rows in the **fit years** are sampled **by class**, and each kept row gets a **weight = 1 / share kept** to undo the sampling ([config.yaml](config.yaml), `model.sample`).

Worked example with dev settings (keep 50% of positives, 6% of negatives):

```
                     before     kept                  weight      weighted total
   positives          1,000  →    500  (50%)       ×  1/0.5  = 2    →  1,000
   negatives          9,000  →    540  (6%)        ×  1/0.06 ≈ 16.7 →  9,000
```

The weighted totals match the original, so the model still learns the real balance. Validation and test rows are sampled **uniformly** (dev: 30% of validation rows, 100% of test rows), so their scores reflect the **real positive rate**.

ML analogy: negative subsampling with importance weights.

## 10.6 The models and the baseline

**Persistence baseline**: score = today's `ratio`. "If the water is already hot, a heatwave is likely soon." A strong, honest baseline every model must beat.

**Gradient-Boosted Trees** (Spark MLlib `GBTClassifier`):

- up to 400 trees, depth 6, learning rate 0.05, 80% row subsampling;
- trained on fit + validation rows, with **early stopping** on the validation rows (stops adding trees when validation stops improving; dev used 94 trees, the full run 227).

**Random Forest** (`RandomForestClassifier`): 150 trees, depth 10, √(features) per split, trained on fit rows.

Both are wrapped in a Spark ML `Pipeline`: `VectorAssembler` (puts the 23 columns into one feature vector) → classifier.

**Model choice**: the one with the higher **validation** PR-AUC wins. On the dev box that was the Random Forest. On the full basin it was **GBT** (0.6066 vs 0.6062, practically a tie).

## 10.7 Metrics

### Precision, recall, F1 — a worked example

Imagine 1,000 test cell-days, 167 of which really are followed by a heatwave (positive rate 16.7%). The model warns on 180 of them; 97 of those warnings are right.

```
                        really positive   really negative
   model warns               97 (TP)           83 (FP)        → 180 warnings
   model silent              70 (FN)          750 (TN)
                            167              833

   precision = TP / warnings          = 97 / 180 = 0.54   "how many warnings were right"
   recall    = TP / real positives    = 97 / 167 = 0.58   "how many heatwaves were caught"
   F1        = 2·P·R / (P + R)        = 0.56
```

### PR-AUC (main metric)

The model gives a **score**; moving the warning threshold trades precision against recall. The **PR curve** plots this trade-off; PR-AUC is the area under it.

```
   precision
   1.0 |●
       |  ●●
       |     ●●●
   0.5 |         ●●●●
       |              ●●●●●●
 0.167 |- - - - - - - - - - - - - -  ← a RANDOM guess scores the positive rate
       +──────────────────────────── recall
       0                          1.0
```

- **A random guess scores the positive rate** (0.167 here), not 0.5.
- **ROC-AUC** is also reported, but it looks good easily when negatives dominate, so PR-AUC is the honest main metric for rare events.

### The warning threshold

Chosen as the threshold with the **best F1 on the validation years**, then applied unchanged to the test years. The test years are never used for any choice.

### The strict-onset subset

Some eligible days already have the water above the threshold (`run_len` 1–4): those are easier, because the heatwave may already be starting. The **strict-onset subset** keeps only days with `run_len = 0` (water still **below** the threshold today) — the hardest, "true onset" case. Scores are reported for both.

## 10.8 Spatial cross-validation

Neighbouring cells are also near-copies (**spatial autocorrelation**). To check that the model works in **regions it never saw**, the fit years are split into 5 folds by **ecoregion** (or sector for open-ocean cells):

```
   fold 0: train on all regions EXCEPT group 0 → score group 0 (validation years)
   fold 1: train on all regions EXCEPT group 1 → score group 1
   …                                                       (switched on for the full run only)
```

```
   random split of cells:                 spatial split by region:
   ●○●○●○  train/test cells side by side   ●●●●|○○○   whole regions held out
   → test cells have training neighbours    → a real test of transfer to new places
```

## 10.9 First results (dev box, PC, new model)

These were the first numbers, from the small dev box. **Quote the full-basin numbers in 10.10**, not these.

Test years 2019–2025: 4.08 M rows, positive rate **16.7%**; strict-onset subset positive rate **10.4%**.

| | PR-AUC (all rows) | PR-AUC (strict onset) | ROC-AUC | Precision | Recall | F1 |
|---|---|---|---|---|---|---|
| Random guess | 0.167 | 0.104 | 0.5 | | | |
| Persistence | 0.586 | 0.277 | – | 0.542 | 0.559 | 0.551 |
| **Random Forest (chosen)** | **0.616** | 0.297 | 0.867 | 0.537 | 0.586 | 0.560 |
| GBT | 0.614 | 0.301 | 0.865 | 0.496 | 0.619 | 0.551 |

How to read it:

- Both models beat persistence, but **modestly** (+0.03 PR-AUC; strict onsets 0.297 vs 0.277). Most of the signal is "the water is already warm".
- These numbers are **not comparable** with the old ones in the report: different rows and task.
- The lab's scikit-learn version reached 0.623 / 0.320 — the Spark models are close to it.

Most important features (Random Forest, dev):

```
   run_len             ██████████████████  0.18
   nb_ratio            █████████████       0.13
   nb_exceed           ██████████          0.10
   days_since_exceed   █████████           0.09
   nb_ratio_21         ████████            0.08
   nb_ratio_7          ██████              0.06
   ratio               █████               0.05
```

Interpretation: how long the water has been above the threshold, and how warm the **surrounding** water is. Heatwaves tend to spread in from warm surroundings.

**Lakshadweep case study (dev, new model)**: the heatwave began **12 May 2023**; the score first crossed the threshold on **7 May** → **5 days** of warning.

## 10.10 Final results (full basin, DGX, 9 Nov 2026) — the numbers to quote

These are the numbers in the report and the presentation. Sources: [outputs/full/tables/model_metrics.json](outputs/full/tables/model_metrics.json), [trust_checks.json](outputs/full/tables/trust_checks.json), [trust_by_year.csv](outputs/full/tables/trust_by_year.csv), [feature_importance.csv](outputs/full/tables/feature_importance.csv), [case_study_summary.json](outputs/full/tables/case_study_summary.json).

**How we know this run used the leak-free code** (checked 11 Nov 2026):

- The metrics file lists the 23 new features (for example `gap_to_thr_ahead` and `nb_confirmed`) and the new task ("not in a confirmed heatwave"). The old leaky version had neither.
- The DGX run log ([outputs/full/dashboard/run_log.csv](outputs/full/dashboard/run_log.csv)) shows Stage E **rebuilding every feature table from scratch** on 9 Nov (15:54–16:06), after `dgx/push_model_v2.ps1` uploaded the fixed code and deleted the old tables. Then come GBT training (17 min), Random Forest (6 min), the trust checks and the case study.
- All metric files are dated 9 Nov, after the fix (8 Nov). The leakage audit found 0 mismatches ([experiments/results/leakage_audit.txt](experiments/results/leakage_audit.txt)).

Test years 2019–2025: **32.1 M rows**, positive rate **13.9%**. The strict-onset subset has 29.0 M rows with a positive rate of **8.4%**.

| | PR-AUC (all rows) | PR-AUC (strict onset) | ROC-AUC | Precision | Recall | F1 |
|---|---|---|---|---|---|---|
| Random guess | 0.139 | 0.084 | 0.5 | | | |
| Persistence | 0.598 | 0.260 | – | 0.574 | 0.546 | 0.560 |
| Random Forest | 0.625 | 0.276 | 0.883 | 0.556 | 0.579 | 0.567 |
| **GBT (chosen)** | **0.625** | **0.276** | **0.884** | 0.562 | 0.568 | 0.565 |

Warning threshold 0.228, chosen on the validation years. The GBT used 227 trees.

**Trust checks**:

- **Bootstrap** (1,000 resamples, 357 blocks, 20% sample of test rows): model 0.625 (95% CI 0.612–0.636), persistence 0.598 (0.584–0.610). The **gain is +0.022 to +0.032**, and the model was better in all 1,000 resamples.
- **Every test year** the model beat persistence (7 of 7):

```
   year   model   rule
   2019   0.614   0.578
   2020   0.616   0.582
   2021   0.539   0.511
   2022   0.592   0.579
   2023   0.661   0.647
   2024   0.692   0.690   ← almost a tie: in the record year the water was hot everywhere
   2025   0.603   0.591
```

- **Regions**: the model was better in 49 of 51 regions.
- **Spatial CV** (whole region groups held out): 0.585–0.616, mean **0.606**, the same as on the validation years (0.607). The model is not memorising places.
- **Lead time** (30,806 onsets in 1,145 sample cells): the model warned before 60% of onsets, and when it warned the median lead was **5 days**. The rule warned before more onsets (65%) but less early (median 4 days). The model gave ≥ 5 days of warning more often (35% vs 31%).

Most important features (GBT, full basin):

```
   nb_ratio_7          ██████████████████████████  0.26   neighbour heat, 7×7 box
   nb_ratio            █████████████████           0.17   neighbour heat, 8 cells
   nb_ratio_21         ██████████████              0.14   neighbour heat, 21×21 box
   nb_ratio_max_7      ██████████                  0.10   hottest neighbour, 7×7
   days_since_exceed   ███████                     0.07
   nb_exceed_21        ███                         0.03
   ratio_30            ███                         0.03
```

Note the change from the dev box: on the full basin the **surrounding water** dominates (the top four are all neighbour features). On the dev box `run_len` came first. The message is the same: heatwaves spread in from warm surroundings.

**Lakshadweep case study (full basin, GBT)**: cell 579170. The heatwave began **12 May 2023**, and the risk score first crossed the threshold on **7 May**, so that's **5 days** of warning (2023 is a test year the model never saw).

**Old numbers to forget**: the leaky first version gave Random Forest 0.295 and GBT 0.316 (on a different task). Don't quote those anywhere.

## Summary of Lesson 10

- Task: will a cell that isn't in a confirmed heatwave be in one within 7 days?
- The old model **leaked** future information (hindsight flag, late climate indices); the lab showed it fell below persistence once fixed; Stage E was rebuilt.
- 23 real-time features: the cell's own history + the surrounding water at 3 scales; no location, season or climate indices; audited with 0 mismatches.
- **Time split** (fit ≤2014, validation 2015–18, test 2019+) and **spatial CV** handle autocorrelation.
- Thinning with weights; **PR-AUC** vs a **persistence** baseline; threshold chosen on validation.
- Honest result (full basin): GBT PR-AUC 0.625 vs persistence 0.598, a small but real gain (+0.022 to +0.032, better in every test year). 5-day warning at Lakshadweep 2023.

**Quick check**

1. Why is `gap_to_thr_ahead` not leakage? *Answer: it uses only the fixed climatology/threshold, known in advance, plus today's SST.*
2. A model has PR-AUC 0.20 on a test set with positive rate 0.17. Good? *Answer: barely better than random (0.17); compare with persistence before claiming anything.*

---

# Lesson 11: Results, dashboard and limitations

All numbers are from the **full run of 4 Nov 2026** (the valid run, after the download fix), unless marked "dev".

## The lesson in one picture: the data funnel

```
   937,485,714  cell-days                      (Stage A: 58,334 cells × 16,071 days)
        │  Hobday detection
        ▼
    66,466,009  heatwave cell-days in clusters   (Stage B/C: 7.2% of cell-days are heatwave days)
        │  daily DBSCAN + Sedona footprints
        ▼
       291,272  daily footprints                 (Stage C)
        │  ST_Intersects links + union-find
        ▼
        14,472  events                           (Stage C)
        │
        ▼
         3 regimes · 59 rules · 1 warning model · 1 case study
        │
        ▼
     ≈ 110 MB  of dashboard files                (export)
```

## 11.1 Data and processing

| Check | Result |
|---|---|
| Rows | 937,485,714 |
| Duplicates / nulls | 0 / 0 |
| Heatwave cell-days | 7.2% |
| Full pipeline time on the DGX (`local[48]`) | ≈ 81 minutes |

Where the 81 minutes went (old model version). The rebuilt model on 9 Nov took about 36 minutes for Stage E: features 12 min, GBT with early stopping 17 min, Random Forest 6 min.

```
   ingest (A)               ███████████                 11 min   (≈12 s per year)
   detection (B)            ███                          3.3 min (all 58,334 climatologies!)
   clusters+footprints+links (C)  ██                     2.1 min
   Random Forest + 5-fold CV ██████████████████████████████████████  38 min
   GBT + 5-fold CV          ████████████████             16 min
   other (features, D, F, export)  ██████████            ≈ 10 min
```

Model training dominates; the "big data" parts (A–C) are fast thanks to buckets and `applyInPandas`.

## 11.2 The long-term trend

Average heatwave days per ocean cell per year:

```
   1982–1991   ██████████                                       9.6
   1992–2001   ███████████                                     11.3
   2002–2011   ███████████████████                             19.3
   2012–2021   ███████████████████████████████████████████     43.3
   2016–2025   ████████████████████████████████████████████████████████████  60.5
```

- Trend: **+14.9 days per decade**.
- Peak years (match strong El Niño / positive IOD): 1998 (44 days), 2010 (47), 2016 (75), 2023 (79), **2024 (133 = record)**.
- In 2024 the average cell spent more than a third of the year in a heatwave. By sector: Bay of Bengal 173 days, Arabian Sea 165, Equatorial 144, South-west 135, Andaman/SCS edge 121, South-east 99.
- **6 February 2024**: **55.6%** of the ocean area was in a heatwave at the same time (32,119 cells: 25,390 Moderate, 6,100 Strong, 579 Severe, 50 Extreme).
- Lakshadweep sample box: 7.7 days/year (1982–91) → 75.5 days/year (2016–25), nearly tenfold.

Part of this rise comes from the **fixed baseline** (Lesson 3.7): warming alone pushes SST over a fixed threshold more often.

## 11.3 Events, regimes and rules

- **14,472 events**; median 7 days; 74% ≤ 10 days; 560 ≥ 30 days; 55 ≥ 100 days.
- Events per decade don't rise (2,613 in the 1980s … 3,401 in the 2010s); instead events got **bigger and longer**, because patches merge.
- Largest events (by cumulative intensity) last 1–3 years: E-2014-009 (2014–16), E-2023-028 (2023–25, still active), E-2018-234 (2018–21), E-1997-261 (1997–98).
- **3 regimes**, silhouette 0.26 (weak); regime shares barely change with IOD/ENSO.
- **59 rules**, all → Moderate, best lift 1.21 (weak).

## 11.4 Model and case study

See Lesson 10.10. Full basin, rebuilt model: GBT PR-AUC **0.625** vs persistence **0.598** (gain +0.022 to +0.032, 95% CI). It was better in 7 of 7 test years and 49 of 51 regions. It gave a warning 5 days before the 12 May 2023 Lakshadweep heatwave.

## 11.5 The dashboard

[dashboard/app.py](dashboard/app.py), built with **Streamlit** (web apps written in plain Python) and **pydeck** (fast WebGL maps).

```
   ┌──────────────────────────────────────────────────────────────────────┐
   │ Hot Oceans                                                            │
   │ Marine heatwaves across the Indian Ocean · OISST v2.1 · 1982–2025     │
   │ Date [────────●─────────────] 2024-01-01      Show [Moderate and above]│
   │ ┌────────────┬────────┬──────────┬──────────┬────────────┬──────────┐ │
   │ │Heatwave map│ Events │ Trends & │Week-ahead│Lakshadweep │ Model &  │ │
   │ │            │        │ drivers  │  risk    │  2023–24   │  rules   │ │
   │ └────────────┴────────┴──────────┴──────────┴────────────┴──────────┘ │
   │  45.9% of ocean area   Strongest: Severe   Mean anomaly: +1.37 °C     │
   │  ┌──────────────────────────────────────────────────────────────┐    │
   │  │      map: each 0.25° cell coloured by category (hover = values)│    │
   │  └──────────────────────────────────────────────────────────────┘    │
   └──────────────────────────────────────────────────────────────────────┘
```

| Tab | Shows |
|---|---|
| Heatwave map | any day of 2023–24; cells coloured Moderate → Extreme; % of ocean area in a heatwave, strongest category, mean anomaly |
| Events | all 14,472 events (sortable); the selected event's peak footprint and track |
| Trends & drivers | heatwave days per year; regime tables by IOD phase |
| Week-ahead risk | the model's warning score per cell for the last 30 days of data |
| Lakshadweep 2023–24 | SST, climatology, threshold and warning score; onset vs first warning |
| Model & rules | metrics, feature importance, top rules |

Key design point: the dashboard reads **only** the small files written by [pipeline/export_dashboard.py](pipeline/export_dashboard.py) (~110 MB: 2023–24 daily categories, cells, yearly means, events GeoJSON, risk, tables) — never the 26 GB lake — so it loads in seconds.

Run it on the PC:

```powershell
streamlit run dashboard/app.py -- --mode full
```

## 11.6 The report

Built by code so it can be regenerated after changes:

```
   report/make_figures.py        → report/figures/*.png        (13 figures from the outputs)
   report/screenshot_dashboard.py → dashboard screenshots
   report/build_short_report.js  → Hot_Oceans_Report_253318_v2.docx   (Node + "docx" library)
   report/finalize_report.ps1    → Word updates contents + page numbers → PDF
```

## 11.7 Limitations (know these well)

| # | Limitation | Why it matters | Possible fix |
|---|---|---|---|
| 1 | **Fixed 1991–2020 baseline** | warming → near-permanent "heatwaves" (133 days in 2024) and multi-year events | detrended / moving baseline |
| 2 | **Event chaining** | any overlap links patches → basin-wide multi-year events; convex hulls can cover land | minimum overlap fraction (IoU), concave hulls |
| 3 | **Weak regimes and rules** | silhouette 0.26, lift ≤ 1.21 | lagged climate indices, regional SST patterns |
| 4 | **Modest warning skill** | small gain over persistence; many false alarms | subsurface heat, winds, air–sea fluxes; calibrated probabilities |
| 5 | **Resolution and regions** | 0.25° smooths small atolls; MEOW covers only half the cells | finer data near reefs |
| 6 | **Download corruption** | parallel downloads silently broke 162 days | now checked; sequential downloads |
| 7 | **Serving layer** | PostGIS is loaded and queried, but the load was not timed, and the dashboard reads files rather than the database | time the load; optionally point the dashboard at PostGIS |
| 8 | **Old model leak** | the first model leaked future information | fixed: rebuilt model, full-basin run done 9 Nov 2026 (Lesson 10.10) |

## 11.8 Course mapping

| Course topic | Where in the project | Lesson |
|---|---|---|
| Spark big-data processing | Stages A–E on ~1 billion cell-days | 4 |
| Partitioning | lake by year and by cell bucket | 5 |
| Data cleaning | Stage A (land, range, duplicates) + download validation | 2 |
| MapReduce | per-cell climatology; yearly aggregates | 3, 4 |
| Sedona / spatial SQL | point-in-polygon (A); footprints and `ST_Intersects` linking (C) | 6 |
| Spatial database | PostGIS tables, GiST indexes, `sql/schema.sql` queries | 7 |
| Clustering | DBSCAN (events), K-Means (regimes) | 8, 9 |
| Association rules | FP-Growth | 9 |
| Classification | Random Forest / GBT warning model | 10 |
| Decision support, disaster case study | dashboard; Lakshadweep 2023 | 10, 11 |

## Summary of Lesson 11

- 937.5 M rows → 14,472 events → ~110 MB of dashboard files; ~81 minutes on the DGX.
- Heatwave days rose about sixfold (9.6 → 60.5 per year); 2024 was the record (133 days); 55.6% of the ocean in a heatwave on 6 Feb 2024.
- Regimes and rules are weak; the model's honest gain is modest.
- The dashboard reads only small exported files; the report is built by code.
- Know the 8 limitations and the course mapping table.

**Quick check**

1. Why doesn't the dashboard read the lake directly? *Answer: 26 GB would be far too slow; small exported files load in seconds.*
2. Name two reasons the 2024 number (133 days) is so high. *Answer: real record warmth (El Niño aftermath) and the fixed baseline in a warming ocean.*

---

# Lesson 12: Viva questions with answers

Short model answers. Say them in your own words; the lesson number tells you where to revise.

## How to answer well

```
   1. one-sentence answer           "We split by time, not randomly."
   2. the reason                    "Consecutive days are near-copies, so a random split leaks."
   3. one number or example         "Train to 2014, validate 2015–18, test 2019–25."
   4. (if relevant) the limitation  "Spatial CV checks transfer to unseen regions too."
```

## A. Big picture

**Q1. What does your project do, in one sentence?** *(overview, 11)*
It detects, tracks and predicts marine heatwaves across the Indian Ocean from 44 years of daily satellite sea temperature — 937.5 million cell-days — using Spark, Sedona and Spark MLlib.

**Q2. Why is this a big-data problem?** *(4)*
About a billion rows (~40 GB in memory); each of 58,334 cells needs its own climatology; each of 16,071 days needs spatial clustering; footprints must be joined across days. It doesn't fit in memory or on one core.

**Q3. Why did you drop the coral part?**
Coral survey data was the slowest and riskiest part. With five days available, the target became heatwave onset, which can be built from SST alone with millions of labelled rows.

**Q4. What is the study area and period?** *(1, 2)*
30°S–30°N, 30°E–120°E (the tropical Indian Ocean), 1982–2025, daily, 0.25° grid; baseline 1991–2020.

## B. Data

**Q5. What is OISST?** *(2)*
NOAA's daily 0.25° global SST product, blending satellite infrared (AVHRR) with ships, buoys and Argo floats, gap-filled by optimum interpolation, from 1981 to today.

**Q6. What is a NetCDF file, and how did you download only the Indian Ocean?** *(2)*
A labelled multi-dimensional array (time × lat × lon). OPeNDAP opens the remote file and transfers only the requested slice; we requested the box one month at a time.

**Q7. How did you clean the data?** *(2)*
Dropped land/missing values, kept −2 to 40 °C, removed duplicate (cell, date) rows; then verified 0 duplicates and 0 nulls over all 937.5 M rows.

**Q8. What went wrong with the download and how did you detect it?** *(2)*
Parallel OPeNDAP downloads silently returned half-empty months (162 days). The land mask never changes, so every day must have the same number of ocean cells; days with fewer were flagged. Fixed with per-month checks, a raw-file checker and sequential downloads; everything was rebuilt.

**Q9. What is a "cell-day" and a cell ID?** *(1, 2)*
One 0.25° ocean square on one day = one row. The cell ID is `row × 1440 + col` on the global grid (Lakshadweep = 579,170), like flattening pixel indices.

## C. Heatwave science

**Q10. Define a marine heatwave.** *(3)*
Hobday et al. (2016): SST above the seasonally varying 90th-percentile threshold for at least 5 consecutive days; gaps of ≤ 2 days between heatwaves are joined.

**Q11. How is the threshold computed?** *(3)*
For each cell and calendar day: pool the 1991–2020 values within ±5 days (11 days × 30 years = 330 values), take the 90th percentile, then smooth the yearly curve with a 31-day moving average. The mean of the same values is the climatology.

**Q12. Why the 11-day window?** *(3)*
30 values per calendar day are too few for a stable 90th percentile; neighbouring days are nearly identical, so pooling them gives 330 values.

**Q13. How are categories defined?** *(3)*
Ratio = anomaly ÷ (threshold − climatology). 1× Moderate, 2× Strong, 3× Severe, 4× Extreme (Hobday et al. 2018). Dividing by the gap makes categories comparable between steady and variable regions, like a z-score.

**Q14. Why a fixed baseline, and what's the downside?** *(3)*
It's the WMO standard normal and reflects what ecosystems actually experience. Downside: warming makes recent years look like constant heatwaves (133 days in 2024) and chains events. A detrended baseline would isolate short extremes.

**Q15. What are ENSO and the IOD?** *(3)*
Climate see-saws: El Niño (ONI index, ≥ +0.5) warms most of the Indian Ocean months later; the Indian Ocean Dipole (DMI index, ≥ +0.4 positive) warms the west and cools the east.

## D. Spark and storage

**Q16. What is Spark, and what is a partition?** *(4)*
A distributed data engine that splits a table into partitions processed in parallel. We ran local mode: 8 cores on the PC, 48 on the DGX.

**Q17. What is lazy evaluation?** *(4)*
Transformations only build a plan; actions (count, write) execute it after Catalyst optimises it (column pruning, early filters).

**Q18. What is a shuffle, and how did you avoid a giant one?** *(4, 5)*
Moving rows between partitions to group them — expensive. Stage A re-organised data from per-year to per-bucket one year at a time (44 small shuffles), appending to bucket folders.

**Q19. How did you partition the data?** *(5)*
By `cell_bucket = cell_id % 64`: ~911 cells per bucket, all years together, so Stage B processes one bucket at a time and can resume.

**Q20. What is applyInPandas and why use it?** *(4)*
Spark sends each group (one cell, or one day) to Python as a pandas DataFrame; our numpy code runs per group in parallel. The science stays simple and testable while Spark handles scale.

**Q21. Where is MapReduce in your project?** *(4)*
Per-cell climatology (group by cell, reduce to mean and percentile) and yearly heatwave-day averages (group by cell-year, sum; then group by year, mean).

**Q22. Why Parquet?** *(5)*
Columnar, compressed, typed, with chunk statistics: Spark reads only needed columns, skips chunks, and partition folders allow pruning.

**Q23. How are your stages resumable?** *(5)*
Each bucket writes a `_SUCCESS` marker and Stage A keeps a list of finished years; reruns skip them (`--force` redoes everything).

**Q24. Why not use the DGX's GPUs?** *(4)*
The work is file I/O and per-cell time-series arithmetic, which CPUs handle well; GPUs would mostly wait for data.

## E. Spatial

**Q25. Where did you use Sedona?** *(6)*
① point-in-polygon join of cells with MEOW ecoregions (`ST_Contains`); ② footprint polygons (`ST_Union_Aggr` → `ST_ConvexHull` → `ST_Buffer`); ③ linking footprints on consecutive days (`ST_Intersects` self-join).

**Q26. What is WKT? What's a common mistake?** *(6)*
Text form of geometry, e.g. `POINT (72.6 10.6)`. The order is x then y — longitude first.

**Q27. How does a spatial join stay fast?** *(6)*
Spatial partitioning, R-tree indexes, and filter-and-refine (cheap bounding-box test first, exact test only for candidates). Our date condition also limits candidates.

**Q28. Why buffer the convex hull by 0.2°?** *(6)*
So blobs that sit side by side on consecutive days actually overlap and get linked.

**Q29. What is the role of PostGIS?** *(7)*
Serving layer for the small derived tables (cells, footprints, events, regimes) with GiST indexes; heavy processing stays in Spark. The DGX saved them as GeoParquet, and on the PC `load_postgis.py` loaded them into PostGIS 3.4 (58,334 cells, 14,472 events, 291,272 footprints). Spatial queries run in 1–2 s. The dashboard itself reads small exported files, so it needs no database server.

**Q30. What is a GiST index?** *(7)*
A tree of bounding boxes (R-tree-like), so spatial queries skip shapes far from the query area.

**Q31. Geometry vs geography?** *(7)*
Geometry is flat in degrees; geography is on the round Earth in metres — needed for "within 300 km".

## F. Clustering and events

**Q32. Why DBSCAN for daily clusters?** *(8)*
It finds clusters of any shape without choosing k (the number of blobs changes daily) and marks isolated hot cells as noise. eps = 1.5 cells, min_samples = 4.

**Q33. Why your own DBSCAN implementation?** *(8)*
On a grid with eps 1.5, the neighbourhood is exactly the 8 surrounding cells, so DBSCAN = 3×3 convolution count → core cells → connected components → border/noise. Exact, fast, and avoided a scikit-learn crash on Windows. A unit test checks it.

**Q34. How are events tracked over time?** *(8)*
Footprints that intersect on consecutive days are linked; union-find finds connected components; components lasting ≥ 5 days are events (14,472). Like video object tracking.

**Q35. Why are some events years long?** *(8)*
Chaining: any overlap links patches, and with a fixed baseline in a warming ocean warm patches overlap almost continuously. A minimum overlap fraction or a detrended baseline would help.

## G. Regimes and rules

**Q36. How did you choose k in K-Means?** *(9)*
Tried k = 3–8 on standardised features and took the highest silhouette: k = 3, 0.26 — weakly separated regimes.

**Q37. Why log and sin/cos features?** *(9)*
Logs tame very skewed durations and areas; sin/cos make the month cyclic so December is next to January.

**Q38. Explain support, confidence and lift.** *(9)*
Support: share of events with the whole pattern; confidence: P(result | condition); lift: confidence ÷ base rate of the result (1 = no relationship). Our best lift was 1.21.

**Q39. Why FP-Growth instead of Apriori?** *(9)*
FP-Growth compresses transactions into an FP-tree and mines it without generating all candidate item sets, so it scales better.

## H. Model

**Q40. What exactly do you predict?** *(10)*
For each cell-day not in a confirmed heatwave (above threshold 5+ days up to today), whether the cell will be in a heatwave on any of the next 7 days.

**Q41. What leakage did you find and how did you fix it?** *(10)*
The heatwave flag is assigned with hindsight (it needs 5 days). The old row filter and two features used it, and monthly climate indices are published late. Fixed with real-time-only features ("confirmed" defined from the past), dropping the indices, and an audit that recomputes inputs from data cut off at the forecast day — 0 mismatches. Without the leak, the old features fell below persistence.

**Q42. Why no latitude/longitude or season features?** *(10)*
The model would memorise places and seasons instead of physics and transfer badly; ratio features are already normalised per place and date.

**Q43. Why is `gap_to_thr_ahead` allowed?** *(10)*
It uses next week's threshold, which comes from the fixed 1991–2020 climatology and is known in advance, plus today's SST — no future observations.

**Q44. Why PR-AUC instead of accuracy?** *(10)*
Onsets are rare; accuracy and even ROC-AUC look good when negatives dominate. PR-AUC focuses on finding positives; a random guess scores the positive rate.

**Q45. What is the persistence baseline and why include it?** *(10)*
Today's intensity ratio used as the score ("hot today → heatwave soon"). Any model must beat this obvious rule to be useful.

**Q46. Why split by time, and why spatial CV?** *(10)*
Neighbouring days and neighbouring cells are near-copies (autocorrelation); random splits leak near-duplicates into training. The time split mimics forecasting; spatial CV by ecoregion tests unseen regions.

**Q47. Why thin the training data, and how do you correct it?** *(10)*
To keep the table manageable; fit-year rows are sampled by class and each kept row gets weight 1/(share kept), so the weighted class balance matches reality. Validation and test keep the real rate.

**Q48. How was the warning threshold chosen?** *(10)*
The best-F1 threshold on the validation years (2015–2018), applied unchanged to the test years.

**Q49. What is the strict-onset subset?** *(10)*
Test days where the water is still below the threshold today (`run_len = 0`) — the hardest, true-onset case. Full basin: persistence 0.260 vs GBT 0.276 PR-AUC (random guess 0.084). Both are weak here.

**Q50. Which features matter most?** *(10)*
The warmth of the **surrounding water**: on the full basin the top four are all neighbour features (`nb_ratio_7` 0.26, `nb_ratio` 0.17, `nb_ratio_21` 0.14, `nb_ratio_max_7` 0.10), then `days_since_exceed`. Heatwaves spread in from warm surroundings.

**Q51. How good is the model, honestly?** *(10)*
It beats persistence, but modestly: full basin PR-AUC 0.625 vs 0.598, with the gain between +0.022 and +0.032 (bootstrap 95% CI). It was better in all 7 test years. Much of the signal is that the water is already warm. Lakshadweep 2023: warning 5 days before the 12 May onset.

**Q52. GBT vs Random Forest — which did you pick and how?** *(10)*
Whichever had the higher validation PR-AUC. On the full basin that was GBT (0.6066 vs 0.6062, practically a tie; both score 0.625 on test). On the dev box it was the Random Forest. GBT used early stopping on the validation years (227 trees).

## I. Results and wrap-up

**Q53. What are your main findings?** *(11)*
Heatwave days rose from 9.6 to 60.5 per cell per year (+14.9 days/decade), record 2024 (133 days), 55.6% of the ocean in a heatwave on 6 Feb 2024; 14,472 events; weak regimes and rules; a modest but honest warning skill.

**Q54. What does the dashboard show, and why is it fast?** *(11)*
Six tabs: heatwave map, events, trends, week-ahead risk, Lakshadweep, model & rules. It reads only ~110 MB of exported files, never the 26 GB lake.

**Q55. What are the main limitations?** *(11)*
Fixed baseline; event chaining; weak regimes/rules; modest warning skill with false alarms; 0.25° resolution and partial ecoregion coverage; PostGIS load not timed, and the dashboard reads files rather than PostGIS.

**Q56. What would you do next?** *(11)*
Detrended baseline; stricter linking and concave hulls; subsurface, wind and flux predictors; calibrated probabilities; daily automatic updates for an operational monitor.

**Q57. What did you learn?**
Validation matters as much as computing power (silent download corruption, leakage); design storage around how the data is accessed (buckets); always compare with a simple baseline and report weak results honestly.
