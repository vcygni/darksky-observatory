FROM python:3.12-slim AS base

# rasterio, pyproj and shapely wheels bundle GDAL, PROJ and GEOS; rasterio needs libexpat.
RUN apt-get update && apt-get install -y --no-install-recommends libexpat1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY --from=ghcr.io/astral-sh/uv:0.11.7 /uv /usr/local/bin/uv

COPY pyproject.toml .
COPY stargazing_spots/ stargazing_spots/
RUN uv pip install --system --no-cache . && mkdir -p input/portugal output/portugal

ENTRYPOINT ["python", "-m", "stargazing_spots"]

FROM base AS test
RUN uv pip install --system --no-cache ".[test]"
COPY tests/ tests/
ENTRYPOINT []
CMD ["python", "-m", "pytest", "tests/"]
