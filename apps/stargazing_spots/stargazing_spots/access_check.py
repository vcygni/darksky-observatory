"""Night access hints from OSM tags. Heuristics; all scores are design choices."""

from typing import Any

import geopandas as gpd
import pandas as pd

from stargazing_spots.land_cover import LAND_COVER_CLASSES

DEFAULT_SCORE = 0.7

# Feature value -> typical access, looked up in tourism, natural, man_made, amenity (in order).
ACCESS_BY_FEATURE = {
    "viewpoint": "drive_up",
    "camp_site": "drive_up",
    "picnic_site": "drive_up",
    "wilderness_hut": "drive_up",
    "observatory": "drive_up",
    "shelter": "short_walk",
    "peak": "short_walk",
    "hill": "short_walk",
    "ridge": "hike_required",
    "saddle": "hike_required",
    "grassland": "unknown",
    "heath": "unknown",
    "bare_rock": "short_walk",
    "cliff": "short_walk",
}
FEATURE_KEYS = ("tourism", "natural", "man_made", "amenity")
POSITIVE_TAGS = {
    "tourism": ("camp_site", "viewpoint", "picnic_site", "wilderness_hut"),
    "amenity": ("shelter",),
    "leisure": ("nature_reserve",),
}
RESTRICTED_ACCESS = ("private", "no", "customers", "permit")
BARRIERS = ("gate", "lift_gate", "bollard", "fence")
ISLAND_CLASSES = tuple(
    k for k, v in LAND_COVER_CLASSES.items() if v in ("water", "herbaceous_wetland")
)


def _tag(row: pd.Series, key: str) -> str | None:
    value = row.get(key)
    return None if value is None or pd.isna(value) else str(value)


def _assess_row(row: pd.Series) -> tuple[str, bool, str, float]:
    access_type = next(
        (ACCESS_BY_FEATURE[v] for k in FEATURE_KEYS if (v := _tag(row, k)) in ACCESS_BY_FEATURE),
        "unknown",
    )
    accessible, score, warnings = True, DEFAULT_SCORE, []

    if any(_tag(row, k) in values for k, values in POSITIVE_TAGS.items()):
        score = max(score, 0.9)
    if (access := _tag(row, "access")) in RESTRICTED_ACCESS:
        accessible, score = False, 0.0
        warnings.append(f"access={access}")
    if (barrier := _tag(row, "barrier")) in BARRIERS:
        accessible, score = False, 0.1
        warnings.append(f"barrier={barrier} (may be locked at night)")
    if _tag(row, "lit") == "yes":
        warnings.append("lit=yes (local light pollution)")
        score = min(score, 0.5)

    if row.get("dem_elevation_m") == 0 and row.get("land_cover_class") in ISLAND_CLASSES:
        access_type, score = "boat_required", 0.3
        warnings.append("offshore island (boat access only)")

    if access_type == "drive_up":
        score = min(score + 0.1, 1.0)
    elif access_type == "hike_required":
        score = min(score, 0.5)
        warnings.append("may require hiking (no nearby road)")
    return access_type, accessible, "; ".join(warnings), round(score, 2)


def assess_access(spots: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Add ``access_type``, ``night_accessible``, ``access_warnings`` and ``access_score``."""
    rows: list[tuple[Any, ...]] = [_assess_row(row) for _, row in spots.iterrows()]
    columns = ("access_type", "night_accessible", "access_warnings", "access_score")
    return spots.assign(**{c: [r[i] for r in rows] for i, c in enumerate(columns)})
