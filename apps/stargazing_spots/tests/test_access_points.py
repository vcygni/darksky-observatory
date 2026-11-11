"""Tests for drivable access-point selection (offline, no OSM extract needed)."""

import pytest

from stargazing_spots.access_points import (
    MAX_WALK_M,
    Road,
    choose_access_point,
    grid_cells,
    haversine_m,
    is_drivable,
    nearest_point_on_road,
    padded_box,
)

SPOT = (40.8666629, -8.2918792)  # Mizarela peak, Serra da Freita

# ~111 m per 0.001 deg latitude; ~84 m per 0.001 deg longitude at 40.87N.
ROAD_EAST_100M = Road(1, "tertiary", "Estrada", ((40.860, -8.2907), (40.873, -8.2907)))
ROAD_FAR_1KM = Road(2, "unclassified", "", ((40.860, -8.2800), (40.873, -8.2800)))


class TestGeometry:
    def test_haversine_one_degree_latitude(self):
        assert haversine_m(40.0, -8.0, 41.0, -8.0) == pytest.approx(111_195, rel=1e-3)

    def test_nearest_point_is_perpendicular_foot(self):
        d, lat, lon = nearest_point_on_road(*SPOT, ROAD_EAST_100M)
        assert d == pytest.approx(haversine_m(*SPOT, SPOT[0], -8.2907), rel=0.01)
        assert lat == pytest.approx(SPOT[0], abs=1e-6)
        assert lon == pytest.approx(-8.2907, abs=1e-6)

    def test_nearest_point_clamps_to_segment_end(self):
        road = Road(3, "tertiary", "", ((40.870, -8.2907), (40.880, -8.2907)))
        _, lat, lon = nearest_point_on_road(*SPOT, road)
        assert (lat, lon) == pytest.approx((40.870, -8.2907), abs=1e-6)


class TestTagClassification:
    @pytest.mark.parametrize(
        "tags,expected",
        [
            # OSRM car.lua speed table
            ({"highway": "tertiary"}, True),
            ({"highway": "trunk"}, True),
            ({"highway": "footway"}, False),
            ({"highway": "path"}, False),
            # OSRM routes unpaved roads (surface only lowers the speed)
            ({"highway": "unclassified", "surface": "gravel"}, True),
            ({"highway": "unclassified", "smoothness": "impassable"}, False),
            # tracks have no speed: routable only with an explicit non-blacklisted access tag
            ({"highway": "track"}, False),
            ({"highway": "track", "tracktype": "grade1", "surface": "asphalt"}, False),
            ({"highway": "track", "motor_vehicle": "yes"}, True),
            ({"highway": "track", "motor_vehicle": "destination"}, False),
            # access hierarchy: motorcar > motor_vehicle > vehicle > access
            ({"highway": "residential", "access": "no", "motor_vehicle": "yes"}, True),
            ({"highway": "residential", "motorcar": "no", "access": "yes"}, False),
            ({"highway": "residential", "access": "yes;private"}, True),
            ({"highway": "residential", "access": "agricultural;forestry"}, False),
            # public access: of OSRM's restricted values only destination
            ({"highway": "residential", "access": "private"}, False),
            ({"highway": "residential", "access": "customers"}, False),
            ({"highway": "residential", "access": "destination"}, True),
            ({"highway": "service", "service": "driveway"}, True),
            ({"highway": "service", "service": "emergency_access"}, False),
            # blocked_ways / avoid_ways
            ({"highway": "construction"}, False),
            ({"highway": "tertiary", "construction": "yes"}, False),
            ({"highway": "tertiary", "construction": "minor"}, True),
            ({"highway": "steps"}, False),
            ({"highway": "service", "area": "yes"}, False),
            # vehicle dimensions (car: 2.0 m high, 1.9 m wide, 4.8 m long, 2 t)
            ({"highway": "service", "maxheight": "1.8"}, False),
            ({"highway": "service", "maxwidth": "1,8"}, False),
            ({"highway": "service", "maxweight": "1.5"}, False),
            ({"highway": "service", "maxheight": "default"}, True),
            # Código da Estrada art. 72.º/75.º: no stopping
            ({"highway": "motorway"}, False),
            ({"highway": "motorway_link"}, False),
            ({"highway": "trunk", "motorroad": "yes"}, False),
        ],
    )
    def test_is_drivable(self, tags, expected):
        assert is_drivable(tags) is expected


class TestChooseAccessPoint:
    def test_nearest_road_point_within_threshold(self):
        ap = choose_access_point(*SPOT, [ROAD_EAST_100M, ROAD_FAR_1KM])
        assert ap.kind == "road"
        assert ap.road_type == "tertiary"
        assert ap.walk_m == round(haversine_m(*SPOT, SPOT[0], -8.2907))
        assert (ap.lat, ap.lon) == pytest.approx((SPOT[0], -8.2907), abs=1e-6)

    def test_road_beyond_threshold_gives_none(self):
        ap = choose_access_point(*SPOT, [ROAD_FAR_1KM])
        assert ap.kind == "none"
        assert ap.lat is None and ap.walk_m is None

    def test_threshold_is_inclusive(self):
        d, _, _ = nearest_point_on_road(*SPOT, ROAD_EAST_100M)
        assert choose_access_point(*SPOT, [ROAD_EAST_100M], max_walk_m=d).kind == "road"
        assert choose_access_point(*SPOT, [ROAD_EAST_100M], max_walk_m=d - 1).kind == "none"

    def test_no_roads(self):
        assert choose_access_point(*SPOT, []).kind == "none"

    def test_default_threshold_is_ground_truth_maximum(self):
        # scripts/derive_access_thresholds.py on official_observation_points.csv
        assert MAX_WALK_M == 358


def test_padded_box_cells_cover_the_reach():
    lat, lon = SPOT
    cells = set(grid_cells(*padded_box(lat, lon, MAX_WALK_M)))
    # a point exactly MAX_WALK_M east of the spot must fall in a covered cell
    east = lon + MAX_WALK_M / (111_320.0 * 0.7566)  # cos(40.87 deg)
    assert next(grid_cells(lat, lat, east, east)) in cells
