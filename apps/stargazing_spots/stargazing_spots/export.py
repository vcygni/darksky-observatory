"""GeoJSON, GeoParquet and Cloud Optimized GeoTIFF writers."""

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import rasterio
import xarray as xr
from rasterio.enums import Resampling
from rasterio.transform import from_bounds

from stargazing_spots import __version__

logger = logging.getLogger(__name__)

NODATA = -9999.0

SPOT_COLUMNS = (
    "geometry",
    "name",
    "id",
    "@id",
    "predicted_sqm",
    "predicted_bortle",
    "predicted_brightness_mcd",
    "ssi_score",
    "ssi_percentile",
    "ssi_class",
    "clear_night_fraction",
    "sky_view_factor",
    "land_cover_class",
    "land_cover_label",
    "land_cover_score",
    "terrain_slope_deg",
    "slope_score",
    "slope_class",
    "dem_elevation_m",
    "pixel_radiance",
    "pixel_stability",
    "pixel_trend",
    "trend_direction",
    "dark_confidence",
    "confidence_class",
    "tier",
    "access_type",
    "access_score",
    "night_accessible",
    "access_warnings",
    "stargazing_score",
    "tourism",
    "natural",
    "leisure",
    "amenity",
    "man_made",
    "ele",
    "region",
)


def to_geojson(gdf: gpd.GeoDataFrame, path: Path, metadata: dict[str, Any] | None = None) -> None:
    """Write the spot columns with lat/lon; null properties are dropped per feature."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.unlink(missing_ok=True)
    out = gdf[[c for c in SPOT_COLUMNS if c in gdf.columns]].copy()
    out["lat"] = out.geometry.y.round(6)
    out["lon"] = out.geometry.x.round(6)
    out.to_file(path, driver="GeoJSON")

    geojson = json.loads(path.read_text())
    for feature in geojson["features"]:
        feature["properties"] = {k: v for k, v in feature["properties"].items() if v is not None}
    if metadata:
        geojson["processing"] = {
            **metadata,
            "generated_at": datetime.now(UTC).isoformat(),
            "pipeline_version": __version__,
            "source_product": "VNP46A4 (Black Marble collection 2)",
        }
    path.write_text(json.dumps(geojson))
    logger.info("Wrote %d spots to %s", len(out), path)


def to_parquet(gdf: gpd.GeoDataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    gdf.to_parquet(path, compression="snappy")


def to_cog(data: xr.DataArray, path: Path, crs: str = "EPSG:4326") -> None:
    """Float32 tiled, deflate-compressed GeoTIFF with average overviews."""
    path.parent.mkdir(parents=True, exist_ok=True)
    x, y = data.coords["x"].values, data.coords["y"].values
    height, width = data.shape
    profile = {
        "driver": "GTiff",
        "dtype": "float32",
        "width": width,
        "height": height,
        "count": 1,
        "crs": crs,
        "transform": from_bounds(
            float(x.min()), float(y.min()), float(x.max()), float(y.max()), width, height
        ),
        "nodata": NODATA,
        "compress": "deflate",
        "tiled": True,
        "blockxsize": 256,
        "blockysize": 256,
    }
    values = data.values.astype(np.float32)
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(np.where(np.isnan(values), NODATA, values), 1)
        dst.build_overviews([2, 4, 8, 16], Resampling.average)
        dst.update_tags(ns="rio_overview", resampling="average")
