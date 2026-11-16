# Validation Data — Portugal

Ground-truth datasets used to validate the PSF skyglow model and pipeline output.

## Data Sources

| File/Directory | Points | Type | Description |
|----------------|--------|------|-------------|
| `stargazing_sites.csv` | 33 | SQM measurements | Published + certified dark-sky sites |
| `expert_recommended_spots.csv` | 20 | Locations | Astrotourism-recommended spots |
| `darkskysites/` | 1,920 | SQM grid | darkskysites.com VIIRS-based reference model |
| `tess-ida/` | 21 sites (20 stations) | Continuous monitoring | Stars4All TESS photometers, 19 sites in Spain, 2 in Portugal |
| `official_observation_points.csv` | 18 | Locations | Official/public stargazing observation points with exact positions (access-point threshold) |

## stargazing_sites.csv

33 sites across mainland Portugal, organized by validation tier:

| Tier | Count | Description | Use |
|------|-------|-------------|-----|
| `measured` | 7 | Published SQM field measurements | Indicative only: 2 pass `published_sites_audit.csv`, 5 excluded |
| `certification_threshold` | 10 | Starlight Foundation certified >= 21.0 | Threshold analysis in `sensitivity.py` only; not used by `validate.py` |
| `estimated` | 16 | Falchi 2016 World Atlas derived | Reference only (not independent) |

**Columns:** WKT, name, region, expected_sqm, sqm_source, sqm_type, description

**Sources:** Lima et al. 2016, IDA certification 2018, Barbosa et al. 2024, Lima 2015 PhD, Dark Sky Alqueva monitoring.

## expert_recommended_spots.csv

20 locations recommended by Portuguese astrotourism organizations and astronomy clubs.

**Columns:** WKT, name, region, recommended_by, description

**Sources:** Dark Sky Alqueva, Visit Portugal, Portuguese astronomy clubs, travel guides.

**Validation use:** None. `validate.py` replaced these town-centre locations with `official_observation_points.csv` (exact positions).

## darkskysites/

VIIRS-based reference sky brightness model from darkskysites.com (LUMIX engine).

- `portugal_grid_sqm_2012_2025.json` — 1,920 points at 0.1° spacing, annual SQM 2012-2025
- `README.md` — API details and download methodology

**Validation use:** Model inter-comparison only. Both models are driven by VIIRS, so this is not validation (`validate.py`: "never as validation").

## tess-ida/

TESS (Telescope Encoder and Sky Sensor) photometer data from the Stars4All European network.

- `IDA/` — Monthly .dat files for 20 stations (2019-2025; not committed)
- `adm/tessida.db` — SQLite database of all readings (not committed)
- `tess_clear_sky.json` — Clear-sky moonless zenith SQM per site, from `scripts/derive_tess_clear_sky.py`
- `tess_station_summary.json` — Superseded per-station summary (not used)
- `.env` — Stars4All NextCloud URL for data download

**Validation use:** Primary source. Per site, the mode of dark (Sun < −18°), moonless readings, compared with the model pixel; 16 pixels fall inside the raster.

See `tess-ida/README.md` for station details and download instructions.

## official_observation_points.csv

18 stargazing observation points designated by an official body (Dark Sky Alqueva, Dark Sky Vale do Tua, Município de Arganil / Góis for Dark Sky Aldeias do Xisto, IDA certification) or public astronomical observatories outside cities. Each was located as an exact OpenStreetMap feature by name (or from official coordinates) — `osm_ref`, `location_method`, `source_url` and `confidence` (12 high, 6 medium) are recorded per row. Points that could only be placed at village level (e.g. the Aldeias do Xisto "viewpoints" above, given at 0.01°) are excluded.

**Use:** derives `MAX_WALK_M` in `access_points.py` (largest distance to a drivable road = 358 m); see `scripts/derive_access_thresholds.py`.

## Corrections (2026-10-08)

| File | Site | Old | New | Evidence |
|------|------|-----|-----|----------|
| stargazing_sites.csv | Dark Sky Alqueva Observatory (Cumeada) | 38.4444, −7.3816 (Monsaraz village) | 38.366954, −7.513822 | OSM node/10798812305; official site 38.3669459, −7.515952 |
| stargazing_sites.csv | Peneda-Gerês (Porta do Mezio) | 41.730, −8.162 (Gerês town) | 41.884849, −8.313127 | OSM way/165541903 "Porta do Mezio" |
| stargazing_sites.csv | Monsaraz (Castle viewpoint) | 38.452, −7.384 | 38.443357, −7.380896 | OSM way/135069846 Castelo de Monsaraz |
| expert_recommended_spots.csv | Cumeada Observatory | 38.43, −7.44 | 38.366954, −7.513822 | as above |

Flagged, not corrected: "Alqueva Lake (eastern shore)" (38.20, −7.80) is Vidigueira town, ~25 km west of the eastern shore; true location unknown.
