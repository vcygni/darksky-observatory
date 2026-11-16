"""Nearest-pixel lookup on regular latitude/longitude grids."""

import numpy as np
import numpy.typing as npt

type FloatArray = npt.NDArray[np.float64]
type IndexArray = npt.NDArray[np.intp]

_CHUNK = 4096  # values per broadcast, bounds memory to CHUNK x len(coords)


def nearest_index(coords: npt.ArrayLike, values: npt.ArrayLike) -> IndexArray:
    """Index of the closest coordinate for each value; ties go to the first, as np.argmin."""
    grid = np.asarray(coords, dtype=np.float64)
    vals = np.asarray(values, dtype=np.float64)
    out = np.empty(vals.shape[0], dtype=np.intp)
    for start in range(0, vals.shape[0], _CHUNK):
        part = vals[start : start + _CHUNK]
        out[start : start + _CHUNK] = np.abs(grid[None, :] - part[:, None]).argmin(axis=1)
    return out


def inside(coords: npt.ArrayLike, values: npt.ArrayLike) -> npt.NDArray[np.bool_]:
    """True where a value lies within the grid extent, including the outer half pixels."""
    grid = np.asarray(coords, dtype=np.float64)
    vals = np.asarray(values, dtype=np.float64)
    half = abs(grid[1] - grid[0]) / 2
    result: npt.NDArray[np.bool_] = (vals >= grid.min() - half) & (vals <= grid.max() + half)
    return result


def sample(
    grid: FloatArray,
    x: npt.ArrayLike,
    y: npt.ArrayLike,
    lon: npt.ArrayLike,
    lat: npt.ArrayLike,
) -> FloatArray:
    """Values of a (y, x) grid at the pixels nearest to each lon/lat."""
    return grid[nearest_index(y, lat), nearest_index(x, lon)]
