"""Stage C — daily DBSCAN clusters → footprint polygons (Sedona) → day-to-day ST_Intersects links
→ union-find → event catalogue (PostGIS `mhw_events`, `mhw_footprints`)."""
from hot_oceans import cli, db, events, grid, runlog  # first: sets PROJ paths on Windows
from hot_oceans.spark import get_spark

import geopandas as gpd  # noqa: E402
import pandas as pd  # noqa: E402
from pyspark.sql import functions as F  # noqa: E402
from shapely import wkt  # noqa: E402
from shapely.geometry import LineString  # noqa: E402

CLUSTER_SCHEMA = "cell_id int, date date, category tinyint, ratio float, anomaly float, cluster int"


def main():
    cfg, args = cli.parse(__doc__)
    ev = cfg["events"]
    spark = get_spark(cfg, "stage-c")

    # 1. Daily clusters of heatwave cells, on grid indices.
    with runlog.timed(cfg, "C", "dbscan", cfg.data("lake", "clusters")) as rec:
        hot = spark.read.parquet(str(cfg.data("lake", "sst_anom"))).filter("category > 0") \
            .select("cell_id", "date", "category", "ratio", "anomaly")

        def cluster(pdf):
            r, c = grid.row_col(pdf.cell_id.to_numpy())
            pdf = pdf.assign(cluster=events.cluster_day(r, c, ev["dbscan_eps_cells"], ev["dbscan_min_samples"]))
            return pdf[pdf.cluster >= 0]

        hot.groupBy("date").applyInPandas(cluster, schema=CLUSTER_SCHEMA) \
            .write.mode("overwrite").parquet(str(cfg.data("lake", "clusters")))
        cl = spark.read.parquet(str(cfg.data("lake", "clusters")))
        rec["rows"] = cl.count()

    # 2. Footprint polygon per (date, cluster) with Sedona.
    with runlog.timed(cfg, "C", "footprints", cfg.data("lake", "footprints")) as rec:
        cl = cl.withColumn("row", (F.col("cell_id") / grid.NCOL).cast("int")) \
               .withColumn("lat", -90 + (F.col("row") + 0.5) * grid.RES) \
               .withColumn("lon", ((F.col("cell_id") % grid.NCOL) + 0.5) * grid.RES) \
               .withColumn("area", (grid.RES * 111.32) ** 2 * F.cos(F.radians("lat")))
        cl.createOrReplaceTempView("cl")
        fp = spark.sql(f"""
            SELECT date, cluster, count(*) AS n_cells, sum(area) AS area_km2,
                   max(category) AS max_cat, max(anomaly) AS max_anom, avg(anomaly) AS mean_anom,
                   sum(area * lat) / sum(area) AS clat, sum(area * lon) / sum(area) AS clon,
                   ST_Buffer(ST_ConvexHull(ST_Union_Aggr(ST_Point(lon, lat))),
                             {ev['footprint_buffer_deg']}) AS geom
            FROM cl GROUP BY date, cluster HAVING count(*) >= {ev['min_footprint_cells']}""")
        fp.write.mode("overwrite").format("geoparquet").save(str(cfg.data("lake", "footprints")))
        fp = spark.read.format("geoparquet").load(str(cfg.data("lake", "footprints")))
        fp.createOrReplaceTempView("fp")
        rec["rows"] = fp.count()

    # 3. Link footprints that overlap on consecutive days (spatial join), then union-find.
    with runlog.timed(cfg, "C", "link") as rec:
        edges = spark.sql("""
            SELECT a.date AS d1, a.cluster AS c1, b.date AS d2, b.cluster AS c2
            FROM fp a JOIN fp b ON b.date = date_add(a.date, 1) AND ST_Intersects(a.geom, b.geom)""").toPandas()
        nodes = spark.sql("SELECT date, cluster, n_cells, area_km2, max_cat, max_anom, mean_anom, clat, clon, "
                          "ST_AsText(geom) AS wkt FROM fp").toPandas()
        key = list(zip(nodes.date, nodes.cluster))
        ev_index = events.link(key, zip(zip(edges.d1, edges.c1), zip(edges.d2, edges.c2)))
        nodes["event"] = [ev_index[k] for k in key]
        rec["rows"], rec["note"] = len(edges), f"{len(nodes)} footprints"

    # 4. Event catalogue.
    with runlog.timed(cfg, "C", "catalogue", cfg.data("lake", "events")) as rec:
        cat = build_catalogue(nodes, ev["min_event_days"])
        rec["rows"] = len(cat)
    cat.drop(columns=["track_wkt", "peak_wkt"]).to_parquet(cfg.data("lake", "events.parquet"))

    gdf = gpd.GeoDataFrame(cat.drop(columns=["peak_wkt", "track_wkt"]), geometry=cat.peak_wkt.map(wkt.loads), crs=4326)
    gdf["track_wkt"] = cat.track_wkt
    cfg.out("dashboard").mkdir(parents=True, exist_ok=True)
    gdf.to_file(cfg.out("dashboard", "events.geojson"), driver="GeoJSON")
    db.write_gdf(cfg, gdf, "mhw_events")
    fp_gdf = gpd.GeoDataFrame(nodes.drop(columns="wkt"), geometry=nodes.wkt.map(wkt.loads), crs=4326)
    db.write_gdf(cfg, fp_gdf, "mhw_footprints")
    spark.stop()


def build_catalogue(nodes: pd.DataFrame, min_days: int) -> pd.DataFrame:
    nodes = nodes.sort_values(["event", "date"])
    rows = []
    for e, g in nodes.groupby("event"):
        daily = g.groupby("date").agg(area=("area_km2", "sum"), clat=("clat", "mean"), clon=("clon", "mean"),
                                      max_anom=("max_anom", "max"), mean_anom=("mean_anom", "mean"))
        if len(daily) < min_days:
            continue
        peak_day = daily.area.idxmax()
        peak = g[g.date == peak_day].sort_values("area_km2").iloc[-1]
        track = list(zip(daily.clon, daily.clat))
        rows.append({
            "start": daily.index.min(), "end": daily.index.max(), "duration_days": len(daily),
            "peak_area_km2": float(daily.area.max()), "max_intensity": float(daily.max_anom.max()),
            "mean_intensity": float(daily.mean_anom.mean()),
            "cum_intensity": float((daily.mean_anom).sum()),        # °C·days, area-mean anomaly summed over days
            "max_category": int(g.max_cat.max()),
            "clat": float(daily.clat.mean()), "clon": float(daily.clon.mean()),
            "start_month": pd.Timestamp(daily.index.min()).month,
            "track_wkt": LineString(track).wkt if len(track) > 1 else None,
            "peak_wkt": peak.wkt,
        })
    cat = pd.DataFrame(rows).sort_values("start").reset_index(drop=True)
    years = pd.to_datetime(cat.start).dt.year
    cat.insert(0, "event_id", [f"E-{y}-{n:03d}" for y, n in zip(years, cat.groupby(years).cumcount() + 1)])
    return cat


if __name__ == "__main__":
    main()
