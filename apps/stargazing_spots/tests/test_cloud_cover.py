"""Solar altitude and clear-night counting for the ERA5 cloud climatology."""

import numpy as np
import pytest

from stargazing_spots.cloud_cover import clear_dark_counts, sun_altitude

# Apparent solar altitude (deg), no refraction: Skyfield 1.55 + JPL DE421.
REFERENCE = [
    ("2024-03-20T21:00:00", 38.72, -9.14, -25.71),  # Lisbon
    ("2024-06-21T22:00:00", 38.72, -9.14, -17.61),
    ("2024-12-21T06:00:00", 38.72, -9.14, -20.91),
    ("2024-09-22T12:00:00", 38.72, -9.14, 50.72),
    ("2024-06-21T22:00:00", 32.65, -16.91, -17.95),  # Funchal
    ("2024-12-21T06:00:00", 32.65, -16.91, -25.68),
    ("2024-03-20T21:00:00", 37.74, -25.67, -13.60),  # Ponta Delgada
    ("2024-06-21T23:30:00", 37.74, -25.67, -21.13),
    ("2024-12-21T06:00:00", 37.74, -25.67, -33.54),
]


@pytest.mark.parametrize("time, lat, lon, expected", REFERENCE)
def test_sun_altitude_matches_ephemeris(time, lat, lon, expected):
    got = sun_altitude(np.array([time], dtype="datetime64[s]"), lat, lon)[0]
    assert abs(got - expected) < 0.6


def test_longitude_changes_darkness():
    # 21:00 UTC at the March equinox: dark in Lisbon, twilight in the Azores.
    t = np.array(["2024-03-20T21:00:00"], dtype="datetime64[s]")
    assert sun_altitude(t, 38.72, -9.14)[0] < -18
    assert sun_altitude(t, 37.74, -25.67)[0] > -18


def test_clear_fraction_counts_hours_not_mean_cover():
    # Ten dark hours on one winter night in Lisbon: 7 clear, 3 overcast.
    times = np.arange(
        np.datetime64("2024-12-21T21:00"), np.datetime64("2024-12-22T07:00"), np.timedelta64(1, "h")
    )
    tcc = np.array([0.0] * 7 + [1.0] * 3).reshape(-1, 1, 1)
    clear, dark = clear_dark_counts(tcc, times, np.array([38.72]), np.array([-9.14]), 0.2)
    assert dark[0, 0] == 10
    assert clear[0, 0] == 7  # mean cover is 0.3, yet 70 % of the dark hours are clear


def test_daylight_and_missing_hours_are_not_counted():
    times = np.array(["2024-06-21T12:00", "2024-12-21T23:00"], dtype="datetime64[s]")
    tcc = np.array([0.0, np.nan]).reshape(-1, 1, 1)
    clear, dark = clear_dark_counts(tcc, times, np.array([38.72]), np.array([-9.14]), 0.2)
    assert dark[0, 0] == 0
    assert clear[0, 0] == 0
