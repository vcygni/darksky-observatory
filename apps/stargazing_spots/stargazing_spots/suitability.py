"""Stargazing Suitability Index (SSI): weighted sum of six scores, 0-100.

Weights, normalisation ranges and class bounds are design choices, not fitted.
"""

from dataclasses import astuple, dataclass

import geopandas as gpd
import numpy as np
import numpy.typing as npt
import pandas as pd

from stargazing_spots.geo import FloatArray

SQM_RANGE = (20.0, 22.0)  # mag/arcsec^2 mapped to 0-1
SVF_FLOOR = 0.5  # SVF at or below scores 0
ELEVATION_CAP_M = 1500.0
SSI_CLASSES = ((80, "excellent"), (65, "good"), (50, "acceptable"), (35, "marginal"))


@dataclass(frozen=True, slots=True)
class SSIWeights:
    darkness: float = 0.30
    clear_sky: float = 0.25
    sky_openness: float = 0.15
    land_cover: float = 0.15
    slope: float = 0.10
    elevation: float = 0.05

    def __post_init__(self) -> None:
        if not np.isclose(sum(astuple(self)), 1.0):
            msg = f"SSI weights must sum to 1, got {sum(astuple(self)):.3f}"
            raise ValueError(msg)


def normalize_darkness(sqm: npt.ArrayLike) -> FloatArray:
    lo, hi = SQM_RANGE
    return np.clip((np.asarray(sqm, dtype=np.float64) - lo) / (hi - lo), 0, 1)


def normalize_clear_sky(fraction: npt.ArrayLike) -> FloatArray:
    return np.clip(np.asarray(fraction, dtype=np.float64), 0, 1)


def normalize_sky_openness(svf: npt.ArrayLike) -> FloatArray:
    return np.clip((np.asarray(svf, dtype=np.float64) - SVF_FLOOR) / (1 - SVF_FLOOR), 0, 1)


def normalize_elevation(elevation_m: npt.ArrayLike) -> FloatArray:
    return np.clip(np.asarray(elevation_m, dtype=np.float64) / ELEVATION_CAP_M, 0, 1)


def ssi_class(score: float) -> str:
    if np.isnan(score):
        return "unknown"
    return next((name for bound, name in SSI_CLASSES if score >= bound), "poor")


def compute_ssi(spots: gpd.GeoDataFrame, weights: SSIWeights = SSIWeights()) -> gpd.GeoDataFrame:
    """Add ``ssi_score`` (0-100, one decimal; NaN without predicted SQM) and ``ssi_class``."""
    elevation = pd.to_numeric(spots["ele"], errors="coerce").fillna(0).to_numpy()
    sqm = spots["predicted_sqm"].to_numpy(dtype=np.float64)
    ssi = (
        weights.darkness * normalize_darkness(sqm)
        + weights.clear_sky * normalize_clear_sky(spots["clear_night_fraction"])
        + weights.sky_openness * normalize_sky_openness(spots["sky_view_factor"])
        + weights.land_cover * np.clip(spots["land_cover_score"].to_numpy(dtype=np.float64), 0, 1)
        + weights.slope * np.clip(spots["slope_score"].to_numpy(dtype=np.float64), 0, 1)
        + weights.elevation * normalize_elevation(elevation)
    ) * 100
    ssi[np.isnan(sqm)] = np.nan
    scores = np.round(ssi, 1)
    return spots.assign(ssi_score=scores, ssi_class=[ssi_class(s) for s in scores])
