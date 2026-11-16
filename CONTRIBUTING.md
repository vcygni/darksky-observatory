# Getting Started

## Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/)
- Docker (optional)
- ~5 GB disk space

## Quick Start

```bash
git clone https://github.com/cygniv404/darksky-observatory.git
cd darksky-observatory
uv sync
cd apps/stargazing_spots && uv sync && cd ../..
make test
```

## Environment Setup

```bash
cp apps/stargazing_spots/.env.example apps/stargazing_spots/.env
```

| Variable | Source | Purpose |
|----------|--------|---------|
| `EARTHDATA_TOKEN` | [urs.earthdata.nasa.gov](https://urs.earthdata.nasa.gov/) | VIIRS data |
| `EDH_TOKEN` | [earthdatahub.destine.eu](https://earthdatahub.destine.eu/) | ERA5 cloud cover |

## Data Acquisition

**Automatic** (first run): Copernicus DEM, ESA WorldCover, Hansen GFC, ERA5 cloud cover.

**One-time setup:**

1. VIIRS: set `EARTHDATA_TOKEN`, pipeline downloads and caches (~50 MB, 5-10 min).
2. OpenStreetMap: `make download-osm`, then `make boundary` (Portugal land boundary from the extract).
3. ERA5: set `EDH_TOKEN`; hourly cloud cover 2006-2025 is read from the Earth Data Hub on first run and the result cached.

## Running the Pipeline

```bash
make run                  # Full pipeline (all regions)

# Manual:
cd apps/stargazing_spots
uv run python -m stargazing_spots \
  --all-regions \
  --from-geojson input/portugal/osm/osm_features_portugal.geojson \
  --output-dir output/portugal \
  --threshold 3.0
```

First run: ~12 min (DEM HTTP reads). With cached terrain: ~36s.

## Validation

```bash
make validate
```

## Docker

```bash
make docker-build
make docker-run
```

## Multi-Country

```bash
mkdir -p apps/stargazing_spots/input/spain/{boundary,cache,osm}
# Add a land boundary + OSM extract for the target country
uv run python -m stargazing_spots --place "Spain" --output-dir output/spain
```

Satellite data (VIIRS, DEM, WorldCover, ERA5) covers all of Europe. Only boundary and OSM features are country-specific.
