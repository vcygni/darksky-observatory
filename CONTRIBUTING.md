# Contributing

## Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)
- Docker (optional)
- ~2.5 GB disk space for input data

## Setup

```bash
git clone https://github.com/vcygni/darksky-observatory.git
cd darksky-observatory
make install
uvx pre-commit install      # optional: ruff, mypy, nbstripout on commit
make lint test
```

## Credentials

```bash
cp apps/stargazing_spots/.env.example apps/stargazing_spots/.env
```

| Variable | Source | Used by |
|----------|--------|---------|
| `EARTHDATA_TOKEN` | [urs.earthdata.nasa.gov](https://urs.earthdata.nasa.gov/) | `make download-viirs` |
| `EDH_TOKEN` | [earthdatahub.destine.eu](https://earthdatahub.destine.eu/) | ERA5 cloud cover, first `make run` (then cached) |

## Input data

```bash
make download-osm     # Geofabrik Portugal extract, MD5-checked
make boundary         # land boundary from the extract
make download-viirs   # VNP46A4 2023-2025, mainland, Madeira, Azores
make download-data    # Copernicus DEM, WorldCover, Hansen tiles over the boundary
```

Without `make download-data` the pipeline reads the same tiles over HTTPS (slower).

## Running

```bash
make run          # all regions, access points, ~2 min with local data
make validate     # validation_report.json
make calibrate    # leave-one-out calibration
```

CLI options: `uv run python -m stargazing_spots --help`.

## Checks

`make lint` runs ruff (all rules), `ruff format --check` and `mypy --strict`; `make test` runs pytest. CI runs the same on Python 3.12 and 3.13.

## Docker

```bash
make docker-build
make docker-test
make docker-run
```
