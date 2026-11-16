"""Download DEM, WorldCover and Hansen tiles over the land boundary (``make download-data``).

Tiles are listed from the boundary (``make boundary``) with the same naming the
pipeline uses (stargazing_spots.tiles). Existing files are kept. About 2 GB.
"""

import logging
import math
import shutil
import urllib.error
import urllib.request
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import geopandas as gpd
from shapely.geometry import box
from shapely.geometry.base import BaseGeometry

from stargazing_spots import tiles
from stargazing_spots.config import BOUNDARY

logger = logging.getLogger(__name__)

TIMEOUT_S = 300
HTTP_NOT_FOUND = 404  # no tile over open sea
WORKERS = 4


def cells(land: BaseGeometry, size: int) -> Iterator[tuple[float, float]]:
    """Centres of the size-degree grid cells that intersect ``land``."""
    west, south, east, north = land.bounds
    for la in range(math.floor(south / size) * size, math.ceil(north), size):
        for lo in range(math.floor(west / size) * size, math.ceil(east), size):
            if land.intersects(box(lo, la, lo + size, la + size)):
                yield la + size / 2, lo + size / 2


def downloads(land: BaseGeometry) -> list[tuple[str, Path]]:
    """(url, local path) for every tile that intersects the land boundary."""
    plan: list[tuple[int, Callable[[float, float], str], Callable[[str], str], Path]] = [
        (1, tiles.dem_name, lambda n: f"{tiles.DEM_URL}/{n}/{n}.tif", tiles.DEM_DIR),
        (
            3,
            tiles.worldcover_name,
            lambda n: f"{tiles.WORLDCOVER_URL}/{n}.tif",
            tiles.WORLDCOVER_DIR,
        ),
        (10, tiles.hansen_name, lambda n: f"{tiles.HANSEN_URL}/{n}.tif", tiles.HANSEN_DIR),
    ]
    return [
        (url_of(name), directory / f"{name}.tif")
        for size, name_of, url_of, directory in plan
        for name in (name_of(la, lo) for la, lo in cells(land, size))
    ]


def fetch(url: str, target: Path) -> None:
    if target.exists():
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    part = target.with_suffix(".tif.part")
    try:
        with urllib.request.urlopen(url, timeout=TIMEOUT_S) as response, part.open("wb") as out:  # noqa: S310 - fixed https hosts
            shutil.copyfileobj(response, out)
    except urllib.error.HTTPError as err:
        part.unlink(missing_ok=True)
        if err.code == HTTP_NOT_FOUND:
            logger.info("No tile: %s", target.name)
            return
        raise
    part.rename(target)
    logger.info("Downloaded %s (%.0f MB)", target.name, target.stat().st_size / 1e6)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    land = gpd.read_file(BOUNDARY).union_all()
    jobs = downloads(land)
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        for future in [pool.submit(fetch, url, path) for url, path in jobs]:
            future.result()


if __name__ == "__main__":
    main()
