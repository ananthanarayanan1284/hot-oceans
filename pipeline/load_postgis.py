"""Load the small result tables (outputs/<mode>/postgis/*.parquet, copied from the DGX) into PostGIS,
then add the indexes in sql/schema.sql. Run on the PC:

    python -m pipeline.load_postgis --env pc --mode full

The connection string comes from config.yaml (postgis.pc) or the HOT_OCEANS_PG_DSN environment variable,
so the password never has to be written into a file."""
import os

from hot_oceans import cli  # first: sets Windows env fixes before numpy is used

import geopandas as gpd  # noqa: E402
import pandas as pd  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402

from hot_oceans.config import ROOT  # noqa: E402


def read_table(path):
    try:
        return gpd.read_parquet(path)       # GeoParquet: has a geometry column
    except (ValueError, KeyError):
        return pd.read_parquet(path)


def main():
    cfg, args = cli.parse(__doc__)
    eng = create_engine(os.environ.get("HOT_OCEANS_PG_DSN") or cfg.postgis_dsn)
    with eng.begin() as c:
        c.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
    files = sorted(cfg.out("postgis").glob("*.parquet"))
    if not files:
        raise SystemExit(f"no tables in {cfg.out('postgis')}; copy outputs/{cfg.mode}/postgis/ from the DGX first")
    for f in files:
        df, table = read_table(f), f.stem
        if isinstance(df, gpd.GeoDataFrame):
            df.to_postgis(table, eng, if_exists="replace", index=False)
            with eng.begin() as c:
                c.execute(text(f"CREATE INDEX IF NOT EXISTS {table}_geom_gix ON {table} USING GIST (geometry)"))
        else:
            df.to_sql(table, eng, if_exists="replace", index=False)
        print(f"[postgis] {table}: {len(df):,} rows")
    # Indexes from schema.sql (the example queries below them are for the report, not run here).
    sql = (ROOT / "sql" / "schema.sql").read_text(encoding="utf-8")
    stmts = ("\n".join(l for l in s.splitlines() if not l.strip().startswith("--")).strip() for s in sql.split(";"))
    with eng.begin() as c:
        for s in stmts:
            if s.startswith("CREATE INDEX"):
                c.execute(text(s))
    print("[postgis] indexes done")


if __name__ == "__main__":
    main()
