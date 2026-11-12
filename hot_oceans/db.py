"""Write derived tables to PostGIS (the 1B-row lake stays in Parquet).

When PostGIS is disabled for this machine (config.yaml postgis.enabled), tables are saved as
(Geo)Parquet under outputs/<mode>/postgis/ instead, so the PC can run the pipeline without a database.
"""


def engine(cfg):
    from sqlalchemy import create_engine
    return create_engine(cfg.postgis_dsn)


def _fallback(cfg, df, table):
    out = cfg.out("postgis", f"{table}.parquet")
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out, index=False)
    print(f"[postgis disabled] saved {len(df)} rows to {out}")


def write_gdf(cfg, gdf, table: str):
    """Replace a spatial table and add a GiST index on its geometry."""
    if not cfg.postgis_enabled:
        return _fallback(cfg, gdf, table)
    from sqlalchemy import text
    eng = engine(cfg)
    gdf.to_postgis(table, eng, if_exists="replace", index=False)
    with eng.begin() as c:
        c.execute(text(f"CREATE INDEX IF NOT EXISTS {table}_geom_gix ON {table} USING GIST (geometry)"))
    print(f"[postgis] wrote {len(gdf)} rows to {table}")


def write_df(cfg, df, table: str):
    if not cfg.postgis_enabled:
        return _fallback(cfg, df, table)
    df.to_sql(table, engine(cfg), if_exists="replace", index=False)
    print(f"[postgis] wrote {len(df)} rows to {table}")
