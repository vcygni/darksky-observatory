"""Terrain at each spot from Copernicus GLO-30: sky view factor, elevation and slope.

terrain_SVF = 1 - mean(sin(max horizon angle)) over 16 azimuths within 1.5 km;
effective_SVF = terrain_SVF * (1 - canopy_fraction). Slope by Horn (1981).
"""

import logging
import math
from collections import defaultdict
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt
import rasterio
from rasterio.windows import Window

from stargazing_spots.geo import FloatArray
from stargazing_spots.tiles import dem_tile

logger = logging.getLogger(__name__)

N_DIRECTIONS = 16  # azimuth rays, design choice
MAX_RADIUS_PX = 50  # 50 x 30 m = 1.5 km, design choice
CELL_SIZE_M = 30.0
SLOPE_RADIUS_PX = 3  # block around the spot for Horn's 3x3 operator

# Ray offsets (direction, step) on the DEM grid; rows grow southwards.
_STEPS = np.arange(1, MAX_RADIUS_PX + 1)
_AZIMUTHS = 2 * np.pi * np.arange(N_DIRECTIONS) / N_DIRECTIONS
_RAY_COLS = np.round(np.sin(_AZIMUTHS)[:, None] * _STEPS).astype(np.intp)
_RAY_ROWS = np.round(-np.cos(_AZIMUTHS)[:, None] * _STEPS).astype(np.intp)
_RAY_DIST = (_STEPS * CELL_SIZE_M).astype(np.float32)


SLOPE_CLASSES = ((5, 1.0, "flat"), (15, 0.8, "gentle"), (30, 0.4, "steep"))  # design choice
STEEPEST = (0.0, "very_steep")
NO_SLOPE = (0.5, "unknown")


def classify_slope(slope_deg: float) -> tuple[float, str]:
    """Score (0-1) and label for a slope in degrees."""
    if math.isnan(slope_deg):
        return NO_SLOPE
    return next(((s, n) for bound, s, n in SLOPE_CLASSES if slope_deg < bound), STEEPEST)


@dataclass(frozen=True, slots=True)
class Terrain:
    svf: FloatArray  # terrain-only sky view factor
    elevation_m: FloatArray
    slope_deg: FloatArray


def sky_view_factor(dem: npt.NDArray[np.float32], row: int, col: int) -> float:
    """Terrain SVF at (row, col); rays stop at the window edge, NaN cells are skipped."""
    z0 = dem[row, col]
    if np.isnan(z0):
        return math.nan
    rows, cols = row + _RAY_ROWS, col + _RAY_COLS
    in_window = (rows >= 0) & (rows < dem.shape[0]) & (cols >= 0) & (cols < dem.shape[1])
    # A straight ray that leaves the window does not re-enter it.
    heights = dem[np.where(in_window, rows, 0), np.where(in_window, cols, 0)]
    angles = np.arctan2(heights - z0, _RAY_DIST)
    angles = np.where(in_window & ~np.isnan(angles), angles, -np.inf)
    horizon = np.maximum(angles.max(axis=1), 0).astype(np.float64)
    return float(np.clip(1.0 - np.mean(np.sin(horizon)), 0, 1))


def horn_slope_grid(
    dem: npt.NDArray[np.float32], cell_m: float = CELL_SIZE_M
) -> npt.NDArray[np.float32]:
    """Slope (degrees) of every cell; edges padded by replication."""
    p = np.pad(dem, 1, mode="edge")
    a, b, c = p[:-2, :-2], p[:-2, 1:-1], p[:-2, 2:]
    d, f = p[1:-1, :-2], p[1:-1, 2:]
    g, h, i = p[2:, :-2], p[2:, 1:-1], p[2:, 2:]
    dzdx = ((c + 2 * f + i) - (a + 2 * d + g)) / (8 * cell_m)
    dzdy = ((g + 2 * h + i) - (a + 2 * b + c)) / (8 * cell_m)
    slope: npt.NDArray[np.float32] = np.degrees(np.arctan(np.sqrt(dzdx**2 + dzdy**2)))
    return slope


def horn_slope(
    dem: npt.NDArray[np.float32], row: int, col: int, radius: int = SLOPE_RADIUS_PX
) -> float:
    """Slope at (row, col) from the surrounding (2 * radius + 1)^2 block of ``dem``."""
    top, left = max(0, row - radius), max(0, col - radius)
    block = dem[top : row + radius + 1, left : col + radius + 1]
    return float(horn_slope_grid(block)[row - top, col - left])


def terrain_at_points(lons: FloatArray, lats: FloatArray) -> Terrain:
    """Read one DEM window per point, grouped by 1-degree tile."""
    n = len(lons)
    svf, elevation, slope = np.full(n, np.nan), np.full(n, np.nan), np.full(n, np.nan)
    by_tile: dict[tuple[int, int], list[int]] = defaultdict(list)
    for i in range(n):
        by_tile[(math.floor(lats[i]), math.floor(lons[i]))].append(i)

    for (tile_lat, tile_lon), indices in sorted(by_tile.items()):
        with rasterio.open(dem_tile(tile_lat, tile_lon)) as src:
            for i in indices:
                row, col = src.index(lons[i], lats[i])
                top, left = max(0, row - MAX_RADIUS_PX), max(0, col - MAX_RADIUS_PX)
                window = Window(
                    left,
                    top,
                    min(2 * MAX_RADIUS_PX + 1, src.width - left),
                    min(2 * MAX_RADIUS_PX + 1, src.height - top),
                )
                dem = src.read(1, window=window)
                r, c = row - top, col - left
                svf[i] = sky_view_factor(dem, r, c)
                elevation[i] = dem[r, c]
                slope[i] = horn_slope(dem, r, c)
    logger.info("Terrain for %d spots from %d DEM tiles", n, len(by_tile))
    return Terrain(svf=svf, elevation_m=elevation, slope_deg=slope)
