"""Sensitivity of the dark-pixel count and area to the radiance threshold."""

import numpy as np
import pandas as pd
import xarray as xr

from stargazing_spots.geo import FloatArray
from stargazing_spots.processing import DEFAULT_THRESHOLD

DEFAULT_THRESHOLDS = (0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 7.0, 10.0)
KM_PER_DEG = 111.32
MIN_ELBOW_POINTS = 3  # a second difference needs three values


def pixel_area_km2(radiance: xr.DataArray) -> FloatArray:
    """Area of each cell of a regular lat/lon grid, shaped like ``radiance``."""
    x, y = radiance.coords["x"].to_numpy(), radiance.coords["y"].to_numpy()
    dx = abs(float(x[1] - x[0])) if len(x) > 1 else 0.0
    dy = abs(float(y[1] - y[0])) if len(y) > 1 else 0.0
    row_area = (dy * KM_PER_DEG) * (dx * KM_PER_DEG * np.cos(np.radians(y)))
    area: FloatArray = np.broadcast_to(row_area[:, None], radiance.shape).copy()
    return area


def run_sensitivity(
    radiance: xr.DataArray, thresholds: tuple[float, ...] = DEFAULT_THRESHOLDS
) -> pd.DataFrame:
    """Dark pixels, area and share of valid pixels for each threshold."""
    valid = ~np.isnan(radiance.to_numpy())
    values = radiance.to_numpy()[valid]
    area = pixel_area_km2(radiance)[valid]
    n = max(len(values), 1)
    rows, previous = [], 0
    for t in sorted(thresholds):
        dark = values < t
        count = int(dark.sum())
        rows.append(
            {
                "threshold_nw": t,
                "dark_pixels": count,
                "dark_area_km2": round(float(area[dark].sum()), 1),
                "dark_pct": round(100 * count / n, 2),
                "marginal_gain_pixels": count - previous,
                "marginal_gain_pct": round(100 * (count - previous) / n, 2),
            }
        )
        previous = count
    return pd.DataFrame(rows)


def find_elbow(table: pd.DataFrame) -> float:
    """Threshold where the marginal gain decelerates most (minimum second difference)."""
    gains = table["marginal_gain_pct"].to_numpy()
    if len(gains) < MIN_ELBOW_POINTS:
        return DEFAULT_THRESHOLD
    return float(table["threshold_nw"].iloc[int(np.argmin(np.diff(gains, n=2))) + 1])


def otsu_threshold(radiance: xr.DataArray, n_bins: int = 256, max_val: float = 20.0) -> float:
    """Histogram threshold with maximum between-class variance (Otsu 1979).

    Radiance above ``max_val`` (cities) is left out so it does not dominate the histogram.
    """
    values = radiance.to_numpy()[~np.isnan(radiance.to_numpy())]
    hist, edges = np.histogram(values[values <= max_val], bins=n_bins, range=(0, max_val))
    centers = (edges[:-1] + edges[1:]) / 2
    total = hist.sum()
    if total == 0:
        return DEFAULT_THRESHOLD
    count, weighted = np.cumsum(hist), np.cumsum(hist * centers)
    best, threshold = 0.0, 0.0
    for i in range(1, n_bins):
        w0 = count[i] / total
        if 0 < w0 < 1:
            m0 = weighted[i] / count[i]
            m1 = (weighted[-1] - weighted[i]) / (total - count[i])
            between = w0 * (1 - w0) * (m0 - m1) ** 2
            if between > best:
                best, threshold = between, float(centers[i])
    return threshold
