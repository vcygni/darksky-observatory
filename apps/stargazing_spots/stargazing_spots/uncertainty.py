"""Per-pixel confidence (0-100) of the dark-sky classification."""

import logging
from dataclasses import dataclass

import geopandas as gpd
import numpy as np
import xarray as xr

from stargazing_spots.geo import sample
from stargazing_spots.processing import TemporalComposite

logger = logging.getLogger(__name__)

HIGH, MEDIUM = 75, 50  # confidence class bounds, design choice


@dataclass(frozen=True, slots=True)
class ConfidenceWeights:
    """Weights of the confidence terms (design choice)."""

    distance: float = 0.4
    stability: float = 0.3
    consistency: float = 0.3


def compute_confidence_layer(
    composite: TemporalComposite,
    threshold: float,
    weights: ConfidenceWeights = ConfidenceWeights(),
) -> xr.DataArray:
    """Confidence for pixels below the threshold; NaN elsewhere.

    distance: sigmoid of (threshold - R) / threshold; stability: 1 - min(sigma / threshold, 1);
    consistency: years below threshold / years.
    """
    radiance = composite.median.values
    distance = 1 / (1 + np.exp(-2.0 * ((threshold - radiance) / threshold) * 5))
    stability = 1.0 - np.clip(composite.stability.values / threshold, 0, 1)
    consistency = composite.consistency.values / max(composite.n_years, 1)
    confidence = (
        weights.distance * distance
        + weights.stability * stability
        + weights.consistency * consistency
    ) * 100
    confidence[~(radiance < threshold)] = np.nan
    return xr.DataArray(
        confidence,
        dims=composite.median.dims,
        coords=composite.median.coords,
        attrs={"units": "percent", "long_name": "dark-sky classification confidence"},
    )


def enrich_spots_with_confidence(
    spots: gpd.GeoDataFrame, confidence: xr.DataArray
) -> gpd.GeoDataFrame:
    """Add ``dark_confidence`` and ``confidence_class`` sampled at each spot."""
    values = sample(
        confidence.values,
        confidence.coords["x"].values,
        confidence.coords["y"].values,
        spots.geometry.x.values,
        spots.geometry.y.values,
    ).astype(np.float64)
    spots = spots.copy()
    spots["dark_confidence"] = values
    spots["confidence_class"] = np.where(
        values > HIGH, "high", np.where(values >= MEDIUM, "medium", "low")
    )
    return spots
