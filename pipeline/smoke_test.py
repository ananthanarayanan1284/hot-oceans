"""Day-1 smoke test: Spark starts with Sedona, a spatial join works, and Parquet can be written.

Run on any machine before the real stages: python -m pipeline.smoke_test [--env pc|dgx]
"""
import shutil
import time

from hot_oceans import cli, runlog
from hot_oceans.spark import get_spark


def main():
    cfg, _ = cli.parse(__doc__)
    t0 = time.time()
    spark = get_spark(cfg, "smoke-test")
    print(f"[smoke] Spark {spark.version} started in {time.time() - t0:.0f}s, master={spark.sparkContext.master}")

    spark.createDataFrame([(1, 72.6, 10.6), (2, 88.0, 15.0), (3, 50.0, -20.0)], ["id", "lon", "lat"]) \
        .createOrReplaceTempView("pts")
    spark.createDataFrame([("Lakshadweep box", "POLYGON((70 8, 75 8, 75 13, 70 13, 70 8))")], ["name", "wkt"]) \
        .createOrReplaceTempView("regions_raw")
    rows = spark.sql("""
        SELECT p.id, r.name
        FROM pts p LEFT JOIN (SELECT name, ST_GeomFromWKT(wkt) AS geom FROM regions_raw) r
          ON ST_Contains(r.geom, ST_Point(p.lon, p.lat))
        ORDER BY p.id""").collect()
    print("[smoke] ST_Contains:", [(r.id, r.name) for r in rows])
    assert rows[0].name == "Lakshadweep box" and rows[1].name is None, "spatial join gave an unexpected result"

    out = cfg.data("tmp", "smoke_parquet")
    spark.range(1000).write.mode("overwrite").parquet(str(out))
    n = spark.read.parquet(str(out)).count()
    print(f"[smoke] wrote and read back {n} rows of Parquet at {out}")
    shutil.rmtree(out, ignore_errors=True)
    runlog.log(cfg, "smoke", "spark_sedona_parquet", rows=n, seconds=round(time.time() - t0, 1), note="ok")
    spark.stop()
    print("[smoke] ALL OK")


if __name__ == "__main__":
    main()
