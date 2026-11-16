"""Radiance change between the annual composites.

With three years this is inter-annual variability, not a trend.
"""

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
import xarray as xr

from stargazing_spots.export import to_cog

CHANGE_THRESHOLD = 1.0  # nW/cm2/sr, design choice


def change_stats(change: xr.DataArray, period: str, threshold: float) -> dict[str, Any]:
    """Pixel counts and summary statistics of a change map."""
    values = change.values[~np.isnan(change.values)]
    n = len(values)
    bright = int(np.sum(values > threshold))
    stable = int(np.sum(np.abs(values) <= threshold))
    dark = int(np.sum(values < -threshold))

    def pct(count: int) -> float:
        return round(100 * count / max(n, 1), 2)

    def stat(func: Callable[..., Any], digits: int) -> float:
        return round(float(func(values)), digits) if n else 0.0

    return {
        "period": period,
        "total_valid_pixels": n,
        "brightening_pixels": bright,
        "brightening_pct": pct(bright),
        "stable_pixels": stable,
        "stable_pct": pct(stable),
        "darkening_pixels": dark,
        "darkening_pct": pct(dark),
        "mean_change_nw": stat(np.mean, 4),
        "median_change_nw": stat(np.median, 4),
        "max_brightening_nw": stat(np.max, 2),
        "max_darkening_nw": stat(np.min, 2),
    }


def write_change_detection(
    layers: list[xr.DataArray],
    labels: tuple[str, ...],
    output_dir: Path,
    threshold: float = CHANGE_THRESHOLD,
) -> None:
    """Write the first-to-last change map and pairwise statistics for three years."""
    first, middle, last = layers
    y0, y1, y2 = labels
    changes = {
        f"{y0}_to_{y1}": middle - first,
        f"{y1}_to_{y2}": last - middle,
        f"{y0}_to_{y2}": last - first,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    to_cog(changes[f"{y0}_to_{y2}"], output_dir / f"change_{y0}_to_{y2}.tif")

    stats: dict[str, Any] = {k: change_stats(v, k, threshold) for k, v in changes.items()}
    a, b = changes[f"{y0}_to_{y1}"], changes[f"{y1}_to_{y2}"]
    stats["trend"] = {
        "consistent_brightening_pixels": int(((a > threshold) & (b > threshold)).sum()),
        "consistent_darkening_pixels": int(((a < -threshold) & (b < -threshold)).sum()),
    }
    (output_dir / "change_stats.json").write_text(json.dumps(stats, indent=2))
