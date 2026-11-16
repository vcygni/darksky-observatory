"""Threshold sensitivity: dark-area accounting."""

import numpy as np
import xarray as xr

from stargazing_spots.sensitivity import _pixel_area_km2, run_sensitivity

STEP = 15 / 3600  # VNP46A4 grid spacing (deg)


def _grid(values, lat0=39.0):
    ny, nx = values.shape
    y = lat0 - np.arange(ny) * STEP
    x = -8.0 + np.arange(nx) * STEP
    return xr.DataArray(values, coords={"y": y, "x": x}, dims=("y", "x"))


def test_pixel_area_follows_latitude():
    area = _pixel_area_km2(_grid(np.zeros((2, 2))))[0, 0]
    expected = (STEP * 111.32) ** 2 * np.cos(np.radians(39.0))
    assert np.isclose(area, expected)
    assert 0.16 < area < 0.17  # not the 0.25 km2 of a 500 m square


def test_dark_area_sums_dark_pixels_only():
    df = run_sensitivity(_grid(np.array([[1.0, 5.0], [1.0, np.nan]])), thresholds=[3.0])
    row = df.iloc[0]
    assert row["dark_pixels"] == 2
    assert np.isclose(
        row["dark_area_km2"], 2 * _pixel_area_km2(_grid(np.zeros((2, 2))))[0, 0], atol=0.05
    )
