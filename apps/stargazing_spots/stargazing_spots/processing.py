"""Multi-year VIIRS composite and dark-sky classification."""

import logging
import warnings
from dataclasses import dataclass

import numpy as np
import xarray as xr

logger = logging.getLogger(__name__)

DEFAULT_THRESHOLD = 3.0  # nW/cm2/sr, design choice; see sensitivity.py


@dataclass(frozen=True, slots=True)
class TemporalComposite:
    """Per-pixel statistics of an annual radiance stack."""

    median: xr.DataArray
    dark_sky: xr.DataArray  # median where below the threshold, else NaN
    stability: xr.DataArray  # standard deviation across years
    trend: xr.DataArray  # last year minus first year
    consistency: xr.DataArray  # number of years below the threshold
    n_years: int


def clean_radiance(radiance: xr.DataArray) -> xr.DataArray:
    """Negative values (fill, artefacts) to NaN."""
    return radiance.where(radiance >= 0)


def classify_temporal(
    radiance_years: list[xr.DataArray], threshold: float = DEFAULT_THRESHOLD
) -> TemporalComposite:
    """Median, spread, change and per-year dark count of co-registered annual grids."""
    stack = np.stack([clean_radiance(r).values for r in radiance_years])
    with warnings.catch_warnings():  # pixels missing in every year stay NaN
        warnings.simplefilter("ignore", RuntimeWarning)
        median = np.nanmedian(stack, axis=0)
        std = np.nanstd(stack, axis=0)
    dark_per_year = (stack < threshold).astype(np.float32)
    dark_per_year[np.isnan(stack)] = np.nan

    template = radiance_years[0]
    coords = {"y": template.coords["y"], "x": template.coords["x"]}

    def grid(values: np.ndarray, name: str) -> xr.DataArray:
        return xr.DataArray(values, dims=("y", "x"), coords=coords, attrs={"long_name": name})

    median_da = grid(median, "median radiance (nW/cm2/sr)")
    composite = TemporalComposite(
        median=median_da,
        dark_sky=median_da.where(median_da < threshold),
        stability=grid(std, "standard deviation across years (nW/cm2/sr)"),
        trend=grid(stack[-1] - stack[0], "last minus first year (nW/cm2/sr)"),
        consistency=grid(np.nansum(dark_per_year, axis=0), "years below threshold"),
        n_years=len(radiance_years),
    )
    logger.info(
        "Dark pixels (median < %.1f): %d of %d",
        threshold,
        int(composite.dark_sky.count()),
        int(median_da.count()),
    )
    return composite
