"""OSM tags selecting candidate features, and the tag-based stargazing score."""

import geopandas as gpd
import pandas as pd

# Candidate nodes are those with any of these key=value tags.
DEFAULT_OSM_TAGS: dict[str, list[str]] = {
    "leisure": ["nature_reserve", "picnic_site"],
    "tourism": ["camp_site", "viewpoint", "picnic_site", "wilderness_hut"],
    "natural": [
        "peak",
        "hill",
        "ridge",
        "saddle",
        "heath",
        "grassland",
        "bare_rock",
        "scree",
        "cliff",
    ],
    "landuse": ["meadow", "grass"],
    "man_made": ["observatory"],
    "amenity": ["shelter"],
}

# Tag score (design choice): elevation in hundreds of metres plus fixed bonuses.
_TOURISM_BONUS = ("viewpoint", "camp_site", "picnic_site")
_LEISURE_BONUS = ("nature_reserve", "park")
_ACCESS_BONUS = ("yes", "permissive")


def _tag_score(ele: object, tourism: object, leisure: object, access: object) -> float:
    score = 0.0
    if ele is not None and str(ele).replace(".", "").isdigit():
        score += float(str(ele)) / 100
    if tourism in _TOURISM_BONUS:
        score += 5
    if leisure in _LEISURE_BONUS:
        score += 3
    if access in _ACCESS_BONUS:
        score += 2
    return score


def score_spots(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Add ``stargazing_score`` and sort by it, highest first."""

    def column(name: str) -> pd.Series:
        return gdf[name] if name in gdf.columns else pd.Series("", index=gdf.index)

    gdf = gdf.copy()
    gdf["stargazing_score"] = [
        _tag_score(*tags)
        for tags in zip(
            column("ele"), column("tourism"), column("leisure"), column("access"), strict=True
        )
    ]
    return gdf.sort_values("stargazing_score", ascending=False)
