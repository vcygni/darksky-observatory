"""Land cover class (ESA WorldCover 2021) and canopy fraction (Hansen GFC) at points."""

import logging
import math
from collections import defaultdict
from collections.abc import Callable

import numpy as np
import numpy.typing as npt
import rasterio
from rasterio.windows import Window

from stargazing_spots.geo import FloatArray
from stargazing_spots.tiles import hansen_tile, worldcover_tile

logger = logging.getLogger(__name__)

TREE_COVER = 10
REMOVED_CLASSES = (50, 80, 95)  # built-up, water, mangroves
HANSEN_NODATA = 255

LAND_COVER_CLASSES = {
    10: "tree_cover",
    20: "shrubland",
    30: "grassland",
    40: "cropland",
    50: "built_up",
    60: "bare_sparse",
    70: "snow_ice",
    80: "water",
    90: "herbaceous_wetland",
    95: "mangroves",
    100: "moss_lichen",
}

# Score per non-tree class (design choice); tree cover scores 1 - canopy fraction.
SUITABILITY = {
    20: 0.8,
    30: 1.0,
    40: 0.6,
    50: 0.0,
    60: 1.0,
    70: 0.5,
    80: 0.0,
    90: 0.4,
    95: 0.0,
    100: 0.8,
}
UNKNOWN_CLASS_SCORE = 0.5


def _read_points(
    lons: FloatArray,
    lats: FloatArray,
    tile_of: Callable[[float, float], str],
    tile_key: Callable[[float, float], tuple[int, int]],
) -> tuple[npt.NDArray[np.uint8], npt.NDArray[np.bool_]]:
    """Pixel value at each point (one-pixel window reads), and whether it was inside its tile."""
    values = np.zeros(len(lons), dtype=np.uint8)
    found = np.zeros(len(lons), dtype=bool)
    groups: dict[tuple[int, int], list[int]] = defaultdict(list)
    for i in range(len(lons)):
        groups[tile_key(lats[i], lons[i])].append(i)
    for indices in groups.values():
        first = indices[0]
        with rasterio.open(tile_of(lats[first], lons[first])) as src:
            for i in indices:
                row, col = src.index(lons[i], lats[i])
                if 0 <= row < src.height and 0 <= col < src.width:
                    values[i] = src.read(1, window=Window(col, row, 1, 1))[0, 0]
                    found[i] = True
    return values, found


def canopy_fraction(lons: FloatArray, lats: FloatArray) -> FloatArray:
    """Hansen tree cover in 2000 as a fraction; 0 outside tiles and on nodata."""
    values, found = _read_points(
        lons,
        lats,
        hansen_tile,
        lambda la, lo: (math.ceil(la / 10) * 10, math.floor(lo / 10) * 10),
    )
    valid = found & (values < HANSEN_NODATA)
    return np.where(valid, values.astype(np.float64) / 100.0, 0.0)


def land_cover_at_points(
    lons: FloatArray, lats: FloatArray, canopy: FloatArray
) -> tuple[npt.NDArray[np.uint8], FloatArray]:
    """WorldCover class (0 outside tiles) and suitability score (NaN outside tiles)."""
    classes, found = _read_points(
        lons,
        lats,
        worldcover_tile,
        lambda la, lo: (math.floor(la / 3) * 3, math.floor(lo / 3) * 3),
    )
    scores = np.array(
        [SUITABILITY.get(int(c), UNKNOWN_CLASS_SCORE) for c in classes], dtype=np.float64
    )
    tree = classes == TREE_COVER
    scores[tree] = np.clip(1.0 - canopy[tree], 0.0, 1.0)
    scores[~found] = np.nan
    logger.info(
        "Land cover: %d spots, %d tree cover",
        len(classes),
        int(tree.sum()),
    )
    return classes, scores
