"""Validate the mainland SQM map and the output spots (``make validate``).

Writes apps/stargazing_spots/output/portugal/validation_report.json.
"""

import geopandas as gpd

from stargazing_spots.config import OUTPUT_DIR, REGIONS
from stargazing_spots.pipeline import load_composite
from stargazing_spots.skyglow import brightness_to_sqm, compute_sky_brightness
from stargazing_spots.validate import run_validation, save_validation_report


def main() -> None:
    median = load_composite(REGIONS["mainland"]).median
    sqm = brightness_to_sqm(compute_sky_brightness(median.values))
    spots = gpd.read_file(OUTPUT_DIR / "spots_all.geojson")
    report = run_validation(sqm, median.coords["x"].values, median.coords["y"].values, spots)
    save_validation_report(report, OUTPUT_DIR / "validation_report.json")
    print(f"TESS clear-sky MAE: {report['baseline']['value']} mag")


if __name__ == "__main__":
    main()
