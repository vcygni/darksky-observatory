.PHONY: install test lint run access-points download-osm validate clean docker-build docker-run

# === Setup ===
install:
	uv sync --all-packages  # root dev group + every workspace member and its dev group

download-data:
	cd apps/stargazing_spots && uv run python scripts/download_terrain_data.py

# OpenStreetMap extract for drivable access points (~425 MB, Geofabrik, updated daily)
OSM_PBF_URL = https://download.geofabrik.de/europe/portugal-latest.osm.pbf
OSM_DIR = apps/stargazing_spots/input/portugal/osm

download-osm:
	curl -fSL -o $(OSM_DIR)/portugal-latest.osm.pbf.part $(OSM_PBF_URL)
	curl -fsSL $(OSM_PBF_URL).md5 | sed 's/portugal-latest.osm.pbf/portugal-latest.osm.pbf.part/' \
		| (cd $(OSM_DIR) && md5sum -c -)
	mv $(OSM_DIR)/portugal-latest.osm.pbf.part $(OSM_DIR)/portugal-latest.osm.pbf

# === Development ===
test:
	uv run python -m pytest apps/stargazing_spots/tests/ -v

lint:
	uv run ruff check apps/stargazing_spots/ scripts/ notebooks/
	uv run ruff format --check apps/stargazing_spots/ scripts/

format:
	uv run ruff format apps/stargazing_spots/ scripts/

# === Pipeline ===
run:
	cd apps/stargazing_spots && uv run python -m stargazing_spots \
		--all-regions \
		--output-dir output/portugal \
		--threshold 3.0

# Re-run only the access-point step on existing output (no satellite processing)
access-points:
	cd apps/stargazing_spots && uv run python -m stargazing_spots.access_points \
		output/portugal/spots_all.geojson

validate:
	cd apps/stargazing_spots && uv run python ../../scripts/run_validation.py

# === Docker ===
docker-build:
	docker compose build stargazing-spots

docker-run:
	docker compose run --rm stargazing-spots

docker-test:
	docker compose run --rm stargazing-spots-test

# === Cleanup ===
clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
