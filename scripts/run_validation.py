"""Validate the PSF sky-brightness model and mainland spots against ground truth.

Same computation the `make validate` target used to inline (it failed with an
IndentationError because Make's tab indentation ends up inside `python -c`).

Usage:
    cd apps/stargazing_spots
    uv run python ../../scripts/run_validation.py
"""

import sys
from pathlib import Path

import geopandas as gpd
import joblib
import numpy as np

APP = Path(__file__).parent.parent / "apps" / "stargazing_spots"
sys.path.insert(0, str(APP))

from stargazing_spots.skyglow import (  # noqa: E402
    PropagationConfig,
    brightness_to_sqm,
    compute_sky_brightness,
)
from stargazing_spots.validate import run_validation, save_validation_report  # noqa: E402


def main() -> None:
    years = [
        joblib.load(APP / f"input/portugal/cache/VNP46A4_{y}.joblib")
        for y in ("2023", "2024", "2025")
    ]
    radiance = np.nanmedian(
        np.stack([d["NearNadir_Composite_Snow_Free"].values[0] for d in years]), axis=0
    )
    x = years[0].coords["x"].values
    y = years[0].coords["y"].values
    sky = compute_sky_brightness(
        np.where(radiance < 0, np.nan, radiance), PropagationConfig()
    )
    sqm = brightness_to_sqm(sky)
    spots = gpd.read_file(APP / "output/portugal/spots_all.geojson")
    report = run_validation(sqm, x, y, spots)
    save_validation_report(report, APP / "output/portugal/validation_report.json")
    print(
        f"Baseline ({report['baseline']['metric']}): {report['baseline']['value']} mag"
    )


if __name__ == "__main__":
    main()
