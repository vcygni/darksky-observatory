
FROM python:3.12-slim AS base

# System deps for GDAL/rasterio/geopandas
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgdal-dev \
    gdal-bin \
    libgeos-dev \
    libproj-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install uv for fast dependency resolution (pinned for reproducible builds)
COPY --from=ghcr.io/astral-sh/uv:0.11.7 /uv /usr/local/bin/uv

# hatchling needs the package source to build, so copy it before installing
COPY pyproject.toml .
COPY stargazing_spots/ stargazing_spots/
RUN uv pip install --system --no-cache .

# Create data directories (/bin/sh has no brace expansion)
RUN mkdir -p input/portugal/cache input/portugal/boundary input/portugal/osm \
             output/portugal/mainland output/portugal/madeira output/portugal/azores \
             output/portugal/visualizations

ENTRYPOINT ["python", "-m", "stargazing_spots"]

# Test image: adds the dev extra (pytest) and the test suite
FROM base AS test
RUN uv pip install --system --no-cache ".[dev]"
COPY tests/ tests/
ENTRYPOINT []
CMD ["python", "-m", "pytest", "tests/", "-v"]
