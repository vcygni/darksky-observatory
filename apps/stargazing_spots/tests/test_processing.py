"""Multi-year composite and dark-sky classification."""

import numpy as np
import xarray as xr

from stargazing_spots.processing import classify_temporal, clean_radiance

Y = np.array([41.0, 40.0])
X = np.array([-8.0, -7.0, -6.0])


def _year(values: list[list[float]]) -> xr.DataArray:
    return xr.DataArray(np.array(values), dims=("y", "x"), coords={"y": Y, "x": X})


YEARS = [
    _year([[1.0, 2.0, 9.0], [-1.0, np.nan, 0.5]]),
    _year([[1.0, 4.0, 9.0], [2.0, np.nan, 0.5]]),
    _year([[1.0, 2.5, 9.0], [2.0, np.nan, 0.5]]),
]


def test_clean_radiance_masks_negatives():
    cleaned = clean_radiance(YEARS[0])
    assert np.isnan(cleaned.values[1, 0])
    assert cleaned.values[0, 0] == 1.0


def test_composite_statistics():
    c = classify_temporal(YEARS, threshold=3.0)
    assert c.median.values[0, 1] == 2.5
    assert c.trend.values[0, 1] == 0.5  # last minus first year
    assert np.isnan(c.trend.values[1, 0])  # first year was negative, so missing
    assert c.consistency.values[0, 1] == 2  # 2.0 and 2.5 below 3.0, 4.0 above
    assert c.n_years == 3


def test_dark_sky_is_median_below_threshold():
    c = classify_temporal(YEARS, threshold=3.0)
    dark = ~np.isnan(c.dark_sky.values)
    assert dark.tolist() == [[True, True, False], [True, False, True]]
