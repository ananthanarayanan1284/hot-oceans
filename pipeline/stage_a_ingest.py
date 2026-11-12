"""Stage A — NetCDF → cleaned long table → Parquet lake (by year, then by cell bucket) + cells table.

Outputs
  lake/sst_by_year/year=YYYY/    cell_id, date, sst, cell_bucket   (one write per year)
  lake/sst_by_cell/cell_bucket=N/ same rows, appended year by year (no single giant shuffle)
  lake/cells/                    GeoParquet: cell_id, lat, lon, geometry, cell_poly, ecoregion, sector, area_km2
  PostGIS table `cells`
"""
from hot_oceans import cli, climate, db, grid, runlog  # first: sets PROJ paths on Windows
from hot_oceans.spark import get_spark

import geopandas as gpd  # noqa: E402
import pandas as pd  # noqa: E402
import xarray as xr  # noqa: E402
from shapely import wkt  # noqa: E402

SST_MIN, SST_MAX = -2.0, 40.0


def read_year(path, box) -> pd.DataFrame:
    ds = xr.open_dataset(path)
    ds = ds.rename({k: v for k, v in {"lat": "latitude", "lon": "longitude"}.items() if k in ds.dims})
    da = ds["sst"].squeeze(drop=True).sortby("latitude")
    da = da.sel(latitude=slice(box["lat_min"], box["lat_max"]), longitude=slice(box["lon_min"], box["lon_max"]))
    df = da.to_dataframe(name="sst").reset_index()
    df = df.dropna(subset=["sst"])                                  # land / fill values
    df = df[(df.sst >= SST_MIN) & (df.sst <= SST_MAX)]               # physical range check
    df["cell_id"] = grid.cell_id(df.latitude.to_numpy(), df.longitude.to_numpy())
    df["date"] = pd.to_datetime(df["time"]).dt.date
    df = df.drop_duplicates(["cell_id", "date"])
    return df[["cell_id", "date", "sst"]].astype({"sst": "float32"})


def main():
    cfg, args = cli.parse(__doc__)
    nb = cfg["grid"]["n_buckets"]
    raw = cfg.data("raw", "oisst")
    by_year, by_cell = cfg.data("lake", "sst_by_year"), cfg.data("lake", "sst_by_cell")
    done_file = by_cell.parent / "_sst_by_cell_years_done.txt"
    done = set(done_file.read_text().split()) if done_file.exists() and not args.force else set()

    spark = get_spark(cfg, "stage-a")
    files = sorted(raw.glob("oisst_*.nc"))
    if not files:
        raise SystemExit(f"no NetCDF files in {raw}; run pipeline.download_oisst first")

    for f in files:
        year = f.stem.split("_")[1]
        if year in done:
            continue
        with runlog.timed(cfg, "A", f"ingest_{year}", by_year / f"year={year}") as rec:
            pdf = read_year(f, cfg.box)
            pdf["cell_bucket"] = grid.bucket(pdf.cell_id.to_numpy(), nb)
            n_days = pdf.date.nunique()
            rec["rows"], rec["note"] = len(pdf), f"{n_days} days, {pdf.cell_id.nunique()} cells"
            (by_year / f"year={year}").mkdir(parents=True, exist_ok=True)
            pdf.to_parquet(by_year / f"year={year}" / "part-0.parquet", index=False)
        with runlog.timed(cfg, "A", f"append_by_cell_{year}", by_cell) as rec:
            spark.read.parquet(str(by_year / f"year={year}")).repartition(nb, "cell_bucket") \
                .write.mode("append").partitionBy("cell_bucket").parquet(str(by_cell))
            rec["partitions"] = nb
        done.add(year)
        done_file.write_text("\n".join(sorted(done)))

    with runlog.timed(cfg, "A", "lake_check") as rec:
        lake = spark.read.parquet(str(by_cell))
        rec["rows"] = lake.count()
        dupes = lake.groupBy("cell_id", "date").count().filter("count > 1").count()
        nulls = lake.filter("sst IS NULL").count()
        rec["note"] = f"duplicates={dupes} nulls={nulls}"

    build_cells(cfg, spark, lake)
    spark.stop()


def build_cells(cfg, spark, lake):
    """Ocean cells with point + 0.25° polygon geometry, tagged with MEOW ecoregion via a Sedona join."""
    with runlog.timed(cfg, "A", "cells", cfg.data("lake", "cells")) as rec:
        cells = lake.select("cell_id").distinct().toPandas()
        lat, lon = grid.center(cells.cell_id.to_numpy())
        cells["lat"], cells["lon"] = lat, lon
        cells["area_km2"] = grid.cell_area_km2(lat)
        cells["sector"] = [climate.sector(a, o) for a, o in zip(lat, lon)]
        spark.createDataFrame(cells).createOrReplaceTempView("cells_raw")

        shp = sorted(cfg.aux("meow").glob("*.shp")) + sorted(cfg.aux("meow").glob("*.geojson"))
        if shp:
            meow = gpd.read_file(shp[0]).to_crs(4326)
            name_col = next(c for c in ("ECOREGION", "ECO_NAME", "ecoregion") if c in meow.columns)
            spark.createDataFrame(pd.DataFrame({"ecoregion": meow[name_col], "wkt": meow.geometry.to_wkt()})) \
                .createOrReplaceTempView("meow_raw")
            spark.sql("SELECT ecoregion, ST_GeomFromWKT(wkt) AS geom FROM meow_raw").createOrReplaceTempView("meow")
            region_join = "LEFT JOIN meow m ON ST_Contains(m.geom, c.geometry)"
            region_col = "m.ecoregion"
        else:
            print("[A] MEOW not found: ecoregion left empty (spatial CV falls back to sectors)")
            region_join, region_col = "", "CAST(NULL AS STRING)"

        out = spark.sql(f"""
            WITH c AS (
              SELECT cell_id, lat, lon, area_km2, sector,
                     ST_Point(lon, lat) AS geometry,
                     ST_PolygonFromEnvelope(lon - 0.125, lat - 0.125, lon + 0.125, lat + 0.125) AS cell_poly
              FROM cells_raw)
            SELECT c.*, {region_col} AS ecoregion FROM c {region_join}""")
        out.write.mode("overwrite").format("geoparquet").save(str(cfg.data("lake", "cells")))
        pdf = out.selectExpr("cell_id", "lat", "lon", "area_km2", "sector", "ecoregion",
                             "ST_AsText(cell_poly) AS wkt").toPandas()
        rec["rows"] = len(pdf)
    gdf = gpd.GeoDataFrame(pdf.drop(columns="wkt"), geometry=pdf.wkt.map(wkt.loads), crs=4326)
    db.write_gdf(cfg, gdf, "cells")


if __name__ == "__main__":
    main()
