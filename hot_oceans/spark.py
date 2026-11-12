"""SparkSession with Apache Sedona registered."""
import os
import sys
from pathlib import Path


def get_spark(cfg, app: str):
    from sedona.spark import SedonaContext

    s = cfg.spark
    Path(s["local_dir"]).mkdir(parents=True, exist_ok=True)
    # Spark workers must use the same Python as the driver (avoids "Python worker failed to connect").
    os.environ.setdefault("PYSPARK_PYTHON", sys.executable)
    os.environ.setdefault("PYSPARK_DRIVER_PYTHON", sys.executable)
    if os.name == "nt" and s.get("hadoop_home"):
        # Windows needs winutils.exe + hadoop.dll for Spark to write files.
        os.environ["HADOOP_HOME"] = s["hadoop_home"]
        os.environ["PATH"] = str(Path(s["hadoop_home"]) / "bin") + os.pathsep + os.environ.get("PATH", "")
    builder = (
        SedonaContext.builder()
        .appName(f"hot-oceans-{app}")
        .master(s["master"])
        .config("spark.driver.memory", s["driver_memory"])
        .config("spark.sql.shuffle.partitions", str(s["shuffle_partitions"]))
        .config("spark.local.dir", s["local_dir"])
        .config("spark.sql.session.timeZone", "UTC")
        .config("spark.sql.execution.arrow.pyspark.enabled", "true")
        .config("spark.serializer", "org.apache.spark.serializer.KryoSerializer")
        .config("spark.kryo.registrator", "org.apache.sedona.core.serde.SedonaKryoRegistrator")
    )
    if s.get("jars"):
        builder = builder.config("spark.jars", s["jars"])  # offline DGX nodes
    else:
        builder = builder.config("spark.jars.packages", s["packages"]).config(
            "spark.jars.repositories", "https://artifacts.unidata.ucar.edu/repository/unidata-all")
    spark = SedonaContext.create(builder.getOrCreate())
    spark.sparkContext.setLogLevel("WARN")
    return spark
