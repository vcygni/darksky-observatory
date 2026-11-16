"""Candidate features on dark pixels, with the pixel's radiance, spread and change."""

import logging

import geopandas as gpd
import numpy as np

from stargazing_spots.change_detection import CHANGE_THRESHOLD
from stargazing_spots.geo import inside, nearest_index
from stargazing_spots.processing import TemporalComposite

logger = logging.getLogger(__name__)

WGS84 = 4326
STABILITY_HIGH, STABILITY_MEDIUM = 0.5, 1.5  # nW/cm2/sr, design choice


def features_on_dark_pixels(
    composite: TemporalComposite, features: gpd.GeoDataFrame, threshold: float
) -> gpd.GeoDataFrame:
    """Point features whose nearest median pixel is below the threshold.

    Duplicates (same name and pixel value) are dropped. Adds ``pixel_radiance``,
    ``pixel_stability``, ``temporal_stability``, ``pixel_trend`` and ``trend_direction``.
    """
    points = features[features.geometry.geom_type == "Point"].copy()
    if points.crs and points.crs.to_epsg() != WGS84:
        points = points.to_crs(epsg=WGS84)

    x = composite.median.coords["x"].values
    y = composite.median.coords["y"].values
    lon, lat = points.geometry.x.values, points.geometry.y.values
    rows, cols = nearest_index(y, lat), nearest_index(x, lon)
    in_extent = inside(y, lat) & inside(x, lon)

    radiance = np.where(in_extent, composite.median.values[rows, cols], np.nan)
    keep = ~np.isnan(radiance) & (radiance < threshold)
    dark = points[keep].assign(pixel_radiance=radiance[keep])
    if "name" in dark.columns:
        dark = dark.drop_duplicates(subset=["name", "pixel_radiance"])
    logger.info("Candidates on dark pixels: %d of %d", len(dark), len(features))

    r, c = nearest_index(y, dark.geometry.y.values), nearest_index(x, dark.geometry.x.values)
    stability = composite.stability.values[r, c].astype(np.float64)
    trend = composite.trend.values[r, c].astype(np.float64)
    return dark.assign(
        pixel_stability=stability,
        temporal_stability=np.where(
            stability < STABILITY_HIGH,
            "high",
            np.where(stability < STABILITY_MEDIUM, "medium", "low"),
        ),
        pixel_trend=trend,
        trend_direction=np.where(
            trend < -CHANGE_THRESHOLD,
            "darkening",
            np.where(trend > CHANGE_THRESHOLD, "brightening", "stable"),
        ),
    )
