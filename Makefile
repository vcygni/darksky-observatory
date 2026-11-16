.PHONY: install download-viirs download-data download-osm boundary run access-points validate calibrate test lint format docker-build docker-run docker-test clean

APP = apps/stargazing_spots
OSM_PBF_URL = https://download.geofabrik.de/europe/portugal-latest.osm.pbf
OSM_DIR = $(APP)/input/portugal/osm

install:
	uv sync --all-packages

# Input data
download-viirs:
	uv run python scripts/download_viirs.py

download-data:
	uv run python scripts/download_terrain.py

download-osm:
	curl -fSL -o $(OSM_DIR)/portugal-latest.osm.pbf.part $(OSM_PBF_URL)
	curl -fsSL $(OSM_PBF_URL).md5 | sed 's/portugal-latest.osm.pbf/portugal-latest.osm.pbf.part/' \
		| (cd $(OSM_DIR) && md5sum -c -)
	mv $(OSM_DIR)/portugal-latest.osm.pbf.part $(OSM_DIR)/portugal-latest.osm.pbf

boundary:
	uv run python scripts/build_boundary.py

# Pipeline
run:
	uv run python -m stargazing_spots

access-points:
	uv run python -m stargazing_spots.access_points $(APP)/output/portugal/spots_all.geojson

validate:
	uv run python scripts/run_validation.py

calibrate:
	uv run python scripts/fit_calibration.py

# Development
test:
	uv run pytest $(APP)/tests

lint:
	uv run ruff check $(APP) scripts notebooks
	uv run ruff format --check $(APP) scripts notebooks
	uv run mypy

format:
	uv run ruff check --fix $(APP) scripts notebooks
	uv run ruff format $(APP) scripts notebooks

docker-build:
	docker compose build

docker-run:
	docker compose run --rm stargazing-spots

docker-test:
	docker compose run --rm stargazing-spots-test

clean:
	find . -type d \( -name __pycache__ -o -name .pytest_cache -o -name .mypy_cache \) -prune -exec rm -rf {} +
