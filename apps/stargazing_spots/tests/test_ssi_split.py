"""Per-region SSI cut: two-class split and percentile."""

import numpy as np

from stargazing_spots.assess import ssi_percentile, two_class_split


def _brute_force_split(values):
    v = np.sort(values)
    best, split = -1.0, None
    for k in range(1, len(v)):
        if v[k] == v[k - 1]:
            continue
        lo, hi = v[:k], v[k:]
        between = len(lo) * len(hi) / len(v) ** 2 * (lo.mean() - hi.mean()) ** 2
        if between > best:
            best, split = between, (v[k - 1] + v[k]) / 2
    return split


def test_split_separates_two_groups():
    values = np.array([40, 41, 42, 43, 70, 71, 72], dtype=float)
    assert two_class_split(values) == 56.5


def test_split_matches_brute_force():
    rng = np.random.default_rng(1)
    values = np.round(rng.normal(58, 9, 300), 1)  # ties included
    assert np.isclose(two_class_split(values), _brute_force_split(values))


def test_split_ignores_missing_and_constant_input():
    assert two_class_split(np.array([np.nan, 1.0, 1.0])) == 1.0
    assert two_class_split(np.array([10.0, np.nan, 30.0])) == 20.0


def test_percentile_is_share_at_or_below():
    ref = np.array([10.0, 20.0, 30.0, 40.0])
    assert np.allclose(ssi_percentile([10, 25, 40], ref), [0.25, 0.5, 1.0])
