"""Spatial thinning must depend only on the set of spots, not on their order."""

import geopandas as gpd
import numpy as np
import pytest
from shapely.geometry import Point

from stargazing_spots.assess import DENSITY_CELL_DEG, DENSITY_MAX_PER_CELL, thin_spatially


def make_spots(lats, lons, ssis, prefix="node/"):
    return gpd.GeoDataFrame(
        {"id": [f"{prefix}{i}" for i in range(len(lats))], "ssi_score": ssis},
        geometry=[Point(lon, lat) for lat, lon in zip(lats, lons, strict=True)],
        crs="EPSG:4326",
    )


@pytest.fixture
def many_spots():
    rng = np.random.default_rng(42)
    n = 400
    return make_spots(
        rng.uniform(38.0, 40.0, n), rng.uniform(-8.5, -7.0, n), rng.uniform(65, 90, n).round(1)
    )


def test_result_is_independent_of_input_order(many_spots):
    reference = set(thin_spatially(many_spots)["id"])
    for seed in range(5):
        shuffled = many_spots.sample(frac=1, random_state=seed)
        assert set(thin_spatially(shuffled)["id"]) == reference


def test_adding_a_spot_only_affects_its_own_cell(many_spots):
    before = thin_spatially(many_spots)
    # A new best spot far south-west of all others: under the old data-anchored
    # grid this shifted every cell; with a fixed grid nothing else may change.
    extra = make_spots([37.13], [-9.07], [99.0], prefix="extra/")
    after = thin_spatially(gpd.GeoDataFrame(pd_concat(many_spots, extra), crs="EPSG:4326"))
    assert set(after["id"]) - set(before["id"]) == {"extra/0"}
    assert set(before["id"]) - set(after["id"]) == set()


def pd_concat(a, b):
    import pandas as pd

    return pd.concat([a, b], ignore_index=True)


def test_non_maximum_suppression_keeps_best_and_chains_correctly():
    # A, B, C on a line ~0.8 km apart; SSI A > B > C.
    # NMS keeps A, suppresses B (within 1 km of A), keeps C (~1.6 km from A).
    lat = 39.0
    step = 0.8 / (111.32 * np.cos(np.radians(lat)))
    spots = make_spots([lat, lat, lat], [-8.0, -8.0 + step, -8.0 + 2 * step], [90.0, 80.0, 70.0])
    assert list(thin_spatially(spots)["id"]) == ["node/0", "node/2"]


def test_ties_are_broken_by_id():
    spots = make_spots([39.0, 39.0001], [-8.0, -8.0], [80.0, 80.0])
    assert list(thin_spatially(spots)["id"]) == ["node/0"]
    assert list(thin_spatially(spots.iloc[::-1])["id"]) == ["node/0"]


def test_density_cap_per_fixed_cell():
    # 120 spots spread so dedup keeps them; 8 of them in one fixed cell.
    rng = np.random.default_rng(1)
    lats = list(rng.uniform(37.0, 42.0, 112)) + [39.01 + 0.02 * k for k in range(8)]
    lons = list(rng.uniform(-9.0, -6.5, 112)) + [-8.24] * 8
    ssis = list(rng.uniform(65, 75, 112)) + [80.0 + k for k in range(8)]
    out = thin_spatially(make_spots(lats, lons, ssis))
    cell = (
        np.floor(out.geometry.y / DENSITY_CELL_DEG),
        np.floor(out.geometry.x / DENSITY_CELL_DEG),
    )
    counts = out.groupby(list(cell)).size()
    assert counts.max() <= DENSITY_MAX_PER_CELL
    in_cell = out[(out.geometry.x == -8.24) & (out.geometry.y >= 39.0) & (out.geometry.y < 39.25)]
    assert sorted(in_cell["ssi_score"]) == [83.0, 84.0, 85.0, 86.0, 87.0]
