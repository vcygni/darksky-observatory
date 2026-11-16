# Getting Started

## Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/)
- Docker (optional)
- ~2.5 GB disk space for input data

## Quick Start

```bash
git clone https://github.com/vcygni/darksky-observatory.git
cd darksky-observatory
make install
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

1. VIIRS: set `EARTHDATA_TOKEN`; the pipeline downloads and caches the annual composites (~50 MB).
2. OpenStreetMap: `make download-osm`, then `make boundary` (Portugal land boundary from the extract).
3. ERA5: set `EDH_TOKEN`; hourly cloud cover 2006-2025 is read from the Earth Data Hub on first run and the result cached.

## Running the Pipeline

```bash
make run                  # Full pipeline (all regions)

# Manual:
cd apps/stargazing_spots
uv run python -m stargazing_spots \
  --all-regions \
  --output-dir output/portugal \
  --threshold 3.0
```

With local input data and a cached cloud climatology, `make run` takes about 2 minutes.

## Validation

```bash
make validate
```

## Docker

```bash
make docker-build
make docker-run
```
