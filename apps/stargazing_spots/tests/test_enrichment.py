"""Tag score and sampling of candidate features on dark pixels."""

import geopandas as gpd
import numpy as np
import xarray as xr
from shapely.geometry import Point

from stargazing_spots.enrichment import score_spots
from stargazing_spots.enrichment_raster import features_on_dark_pixels
from stargazing_spots.processing import classify_temporal


def test_score_spots_values_and_order():
    features = gpd.GeoDataFrame(
        {
            "name": ["view", "park", "plain"],
            "tourism": ["viewpoint", None, None],
            "leisure": [None, "park", None],
            "ele": ["800", None, "abc"],
            "access": ["yes", None, "private"],
        },
        geometry=[Point(0, 0)] * 3,
    )
    scored = score_spots(features)
    assert scored["name"].tolist() == ["view", "park", "plain"]
    assert scored["stargazing_score"].tolist() == [8 + 5 + 2, 3, 0]


def _composite(values: list[list[float]]):
    grid = xr.DataArray(
        np.array(values), dims=("y", "x"), coords={"y": [41.0, 40.0], "x": [-8.0, -7.0]}
    )
    return classify_temporal([grid, grid, grid], threshold=3.0)


def test_features_on_dark_pixels_keeps_dark_points_inside_the_grid():
    composite = _composite([[1.0, 5.0], [2.0, np.nan]])
    features = gpd.GeoDataFrame(
        {"name": ["dark", "bright", "nodata", "outside", "dark-duplicate"]},
        geometry=[
            Point(-8.1, 41.1),
            Point(-7.0, 41.0),
            Point(-7.0, 40.0),
            Point(-5.0, 41.0),  # beyond half a pixel east of the grid
            Point(-7.9, 40.9),  # same pixel and name as "dark" after renaming below
        ],
        crs="EPSG:4326",
    )
    features.loc[4, "name"] = "dark"
    result = features_on_dark_pixels(composite, features, threshold=3.0)
    assert result["name"].tolist() == ["dark"]
    assert result["pixel_radiance"].tolist() == [1.0]
    assert result["trend_direction"].tolist() == ["stable"]
