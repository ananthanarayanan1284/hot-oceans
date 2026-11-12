-- Hot Oceans PostGIS layer. Tables are written by the pipeline (geopandas to_postgis);
-- this file adds indexes and the spatial queries used in the report/viva.
CREATE EXTENSION IF NOT EXISTS postgis;

-- Written by Stage A:  cells(cell_id, lat, lon, area_km2, sector, ecoregion, geometry = 0.25° cell polygon)
-- Written by Stage C:  mhw_footprints(date, cluster, n_cells, area_km2, max_cat, ..., event, geometry)
--                      mhw_events(event_id, start, end, duration_days, peak_area_km2, max_intensity, ..., geometry = peak footprint)
-- Written by Stage D:  event_regimes(event_id, regime, iod_phase, enso_phase)

CREATE INDEX IF NOT EXISTS cells_cell_id_idx ON cells (cell_id);
CREATE INDEX IF NOT EXISTS mhw_footprints_date_idx ON mhw_footprints (date);
CREATE INDEX IF NOT EXISTS mhw_events_start_idx ON mhw_events (start);

-- 1. Which ecoregions were touched by heatwave footprints in April–May 2024?
--    covered_km2_days adds the area of each ecoregion cell under a footprint, once per day it is covered.
SELECT coalesce(c.ecoregion, '(open ocean)') AS ecoregion, count(DISTINCT f.event) AS events,
       round(sum(c.area_km2)::numeric) AS covered_km2_days
FROM mhw_footprints f JOIN cells c ON ST_Intersects(f.geometry, c.geometry)
WHERE f.date BETWEEN '2024-04-01' AND '2024-05-31'
GROUP BY c.ecoregion ORDER BY covered_km2_days DESC;

-- 2. Longest events whose peak footprint lies within 300 km of Lakshadweep.
SELECT event_id, start, duration_days, max_category
FROM mhw_events
WHERE ST_DWithin(geometry::geography, ST_SetSRID(ST_MakePoint(72.64, 10.57), 4326)::geography, 300000)
ORDER BY duration_days DESC LIMIT 10;

-- 3. Regime mix by Indian Ocean Dipole phase.
SELECT iod_phase, regime, count(*) AS n
FROM event_regimes GROUP BY iod_phase, regime ORDER BY iod_phase, regime;
