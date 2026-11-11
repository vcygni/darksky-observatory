"""Validation helpers: no edge clamping, explicit audit decisions, correct statistics."""

import numpy as np
import pandas as pd
import pytest

from stargazing_spots import validate as v

X = np.arange(-9.5, -6.2, 0.5)  # 7 columns, 0.5 deg spacing
Y = np.arange(42.0, 37.0, -0.5)  # 10 rows, north to south
SQM = np.arange(70, dtype=float).reshape(10, 7)


def test_points_outside_raster_are_not_sampled():
    assert np.isnan(v._sample_sqm_map(SQM, X, Y, 39.0, -5.0))  # east of the raster
    assert np.isnan(v._sample_sqm_map(SQM, X, Y, 43.0, -8.0))  # north of the raster


def test_points_inside_raster_hit_the_containing_pixel():
    assert v._pixel_index(X, Y, 42.0, -9.5) == (0, 0)
    assert v._pixel_index(X, Y, 41.6, -9.3) == (1, 0)
    assert v._sample_sqm_map(SQM, X, Y, 41.6, -9.3) == SQM[1, 0]
    # half a pixel beyond the last centre is still inside
    assert v._pixel_index(X, Y, 37.3, -6.3) == (9, 6)


def test_metrics():
    m = v._metrics([21.0, 20.0, 19.0], [20.5, 20.0, 19.5])
    assert m["n"] == 3
    assert m["mae"] == pytest.approx(1 / 3, abs=1e-3)
    assert m["bias"] == pytest.approx(0.0, abs=1e-9)
    assert m["rmse"] == pytest.approx(np.sqrt(0.5 / 3), abs=1e-3)
    assert m["pearson_r"] == pytest.approx(1.0)


def test_measured_site_without_audit_decision_is_rejected(tmp_path, monkeypatch):
    pd.DataFrame(
        {
            "WKT": ["POINT (-8 40)"],
            "name": ["New site"],
            "expected_sqm": [21.0],
            "sqm_type": ["measured"],
        }
    ).to_csv(tmp_path / "stargazing_sites.csv", index=False)
    pd.DataFrame(columns=["name", "use", "value_verified", "location_verified", "reason"]).to_csv(
        tmp_path / "published_sites_audit.csv", index=False
    )
    monkeypatch.setattr(v, "VALIDATION_DIR", tmp_path)
    with pytest.raises(ValueError, match="without an audit decision"):
        v._load_published_sites()


def test_repository_audit_covers_every_measured_site():
    published = v._load_published_sites()
    assert published is not None
    assert set(published["use"]) <= {"primary", "indicative", "excluded"}
