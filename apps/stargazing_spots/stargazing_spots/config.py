"""Paths, regions and years shared by the pipeline and the scripts."""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

APP_DIR = Path(__file__).resolve().parents[1]
INPUT_DIR = APP_DIR / "input" / "portugal"
CACHE_DIR = INPUT_DIR / "cache"
OSM_PBF = INPUT_DIR / "osm" / "portugal-latest.osm.pbf"
BOUNDARY = INPUT_DIR / "boundary" / "portugal_osm.geojson"
OUTPUT_DIR = APP_DIR / "output" / "portugal"

YEARS = ("2023", "2024", "2025")
VIIRS_PRODUCT = "VNP46A4"
VIIRS_VARIABLE = "NearNadir_Composite_Snow_Free"

type RegionName = Literal["mainland", "madeira", "azores"]
type BBox = tuple[float, float, float, float]  # west, south, east, north


@dataclass(frozen=True, slots=True)
class Region:
    name: RegionName
    cache_suffix: str
    viirs_bbox: BBox  # extent of the VIIRS download
    cloud_bbox: BBox  # extent of the ERA5 clear-night climatology


REGIONS: dict[RegionName, Region] = {
    "mainland": Region("mainland", "", (-9.5, 37.0, -6.2, 42.15), (-10.0, 36.5, -6.0, 42.5)),
    "madeira": Region(
        "madeira", "_madeira", (-17.4, 32.5, -16.2, 33.2), (-17.5, 32.0, -16.0, 34.0)
    ),
    "azores": Region("azores", "_azores", (-31.3, 36.9, -25.0, 39.8), (-32.0, 36.5, -25.0, 40.0)),
}


def viirs_cache(region: Region, year: str) -> Path:
    return CACHE_DIR / f"{VIIRS_PRODUCT}_{year}{region.cache_suffix}.joblib"
