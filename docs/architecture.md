# Architecture

## Repository

```
darksky-observatory/
├── apps/stargazing_spots/
│   ├── stargazing_spots/        # Pipeline package (22 modules)
│   └── tests/
├── scripts/                     # Downloads, boundary, TESS reduction, calibration, validation
├── notebooks/portugal/          # Analysis notebooks (3)
├── validation/portugal/         # Ground-truth data
├── docs/
├── Makefile
├── docker-compose.yml
└── pyproject.toml               # uv workspace root; ruff, mypy and pytest config
```

## Data flow

`make run` (`pipeline.run_all`):

1. `osm_extract`: candidate OSM nodes inside the land boundary (one pass over the extract).
2. Per region (`pipeline.run_region`, regions in `config.REGIONS`):
   1. `processing`: three annual composites → median, spread, change, dark-sky mask.
   2. `uncertainty`, `change_detection`: confidence layer and change statistics; COGs written.
   3. `enrichment_raster`, `enrichment`: candidates on dark pixels, tag score.
   4. `assess`: `skyglow` (PSF → SQM), `cloud_cover` (ERA5 clear-night fraction), `terrain` (SVF, elevation, slope), `land_cover`, `access_check`, then `suitability` (SSI).
   5. `assess.select_spots`: physical filters, per-region two-class SSI split, deduplication, density cap.
   6. `export`, `stac_catalog`: GeoJSON, GeoParquet, STAC.
3. Merge regions → `spots_all.geojson`; `access_points` adds the drivable access point per spot.

`scripts/run_validation.py` (`validate`) and `scripts/fit_calibration.py` run on the outputs.

## Modules

| Module | Role |
|--------|------|
| `config` | Paths, regions, years, VIIRS cache names |
| `pipeline` | Per-region run and merged output |
| `processing` | Temporal composite and dark-sky classification |
| `uncertainty` | Per-pixel confidence |
| `change_detection` | Inter-annual radiance change |
| `osm_extract` | Candidate nodes from the local OSM extract |
| `enrichment` | OSM tag selection and tag score |
| `enrichment_raster` | Candidates on dark pixels with pixel statistics |
| `skyglow` | PSF convolution (FFT), SQM, Bortle class |
| `cloud_cover` | ERA5 hourly clear-night fraction |
| `terrain` | Sky view factor, elevation, slope (Copernicus GLO-30) |
| `land_cover` | WorldCover class, Hansen canopy fraction |
| `tiles` | DEM, WorldCover and Hansen tile names and sources |
| `geo` | Nearest-pixel lookup on regular grids |
| `access_check` | Night-access hints from OSM tags |
| `suitability` | SSI weighted linear combination |
| `assess` | Assessment, filters, two-class split, thinning |
| `access_points` | Nearest drivable, legal-to-stop road point |
| `sensitivity` | Threshold sensitivity (`--sensitivity`) |
| `validate` | Comparison with TESS and published SQM |
| `export` | GeoJSON, GeoParquet, COG |
| `stac_catalog` | STAC catalog per region |

## Formats

| Data | Format |
|------|--------|
| VIIRS input | joblib (xarray Dataset on a 15″ lat/lon grid, from blackmarblepy) |
| Rasters | Cloud Optimized GeoTIFF |
| Spots | GeoJSON, GeoParquet |
| Metadata | STAC JSON, `run_metadata.json` |

## Tooling

| Component | Tool |
|-----------|------|
| Environment | uv workspace, Python ≥ 3.12 |
| Lint, format | ruff (all rules, documented ignores) |
| Types | mypy `--strict` |
| Tests | pytest (strict config, warnings as errors) |
| CI | GitHub Actions, Python 3.12 and 3.13 |
| Container | Docker (`base` and `test` targets), docker compose |
