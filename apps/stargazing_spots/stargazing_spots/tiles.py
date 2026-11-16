"""Raster tile sources: a local copy under input/portugal if present, else public HTTPS."""

import math

from stargazing_spots.config import INPUT_DIR

DEM_DIR = INPUT_DIR / "dem"
WORLDCOVER_DIR = INPUT_DIR / "worldcover"
HANSEN_DIR = INPUT_DIR / "hansen"

DEM_URL = "https://copernicus-dem-30m.s3.eu-central-1.amazonaws.com"
WORLDCOVER_URL = "https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map"
HANSEN_URL = "https://storage.googleapis.com/earthenginepartners-hansen/GFC-2023-v1.11"


def _hemi(value: int, pos: str, neg: str, width: int) -> str:
    return f"{pos if value >= 0 else neg}{abs(value):0{width}d}"


def dem_name(lat: float, lon: float) -> str:
    """Copernicus GLO-30 tile (1 deg, named by its south-west corner)."""
    la, lo = math.floor(lat), math.floor(lon)
    return f"Copernicus_DSM_COG_10_{_hemi(la, 'N', 'S', 2)}_00_{_hemi(lo, 'E', 'W', 3)}_00_DEM"


def worldcover_name(lat: float, lon: float) -> str:
    """ESA WorldCover 2021 tile (3 deg, named by its south-west corner)."""
    la, lo = math.floor(lat / 3) * 3, math.floor(lon / 3) * 3
    return f"ESA_WorldCover_10m_2021_v200_{_hemi(la, 'N', 'S', 2)}{_hemi(lo, 'E', 'W', 3)}_Map"


def hansen_name(lat: float, lon: float) -> str:
    """Hansen GFC tree cover 2000 tile (10 deg, named by its north-west corner)."""
    la, lo = math.ceil(lat / 10) * 10, math.floor(lon / 10) * 10
    ns, ew = "N" if la >= 0 else "S", "E" if lo >= 0 else "W"
    return f"Hansen_GFC-2023-v1.11_treecover2000_{abs(la):02d}{ns}_{abs(lo):03d}{ew}"


def dem_tile(lat: float, lon: float) -> str:
    name = dem_name(lat, lon)
    local = DEM_DIR / f"{name}.tif"
    return str(local) if local.exists() else f"{DEM_URL}/{name}/{name}.tif"


def worldcover_tile(lat: float, lon: float) -> str:
    name = worldcover_name(lat, lon)
    local = WORLDCOVER_DIR / f"{name}.tif"
    return str(local) if local.exists() else f"{WORLDCOVER_URL}/{name}.tif"


def hansen_tile(lat: float, lon: float) -> str:
    name = hansen_name(lat, lon)
    local = HANSEN_DIR / f"{name}.tif"
    return str(local) if local.exists() else f"{HANSEN_URL}/{name}.tif"
