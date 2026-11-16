"""Command line: python -m stargazing_spots [options]."""

import argparse
import logging
from pathlib import Path

from dotenv import load_dotenv

from stargazing_spots.config import APP_DIR, OSM_PBF, OUTPUT_DIR
from stargazing_spots.pipeline import RunOptions, run_all
from stargazing_spots.processing import DEFAULT_THRESHOLD


def main() -> None:
    parser = argparse.ArgumentParser(description="Rank stargazing spots in Portugal.")
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument(
        "--threshold",
        type=float,
        default=DEFAULT_THRESHOLD,
        help="dark-sky radiance threshold in nW/cm2/sr (default: %(default)s)",
    )
    parser.add_argument("--osm-pbf", type=Path, default=OSM_PBF, help="OpenStreetMap extract")
    parser.add_argument(
        "--skip-access-points", action="store_true", help="do not add drivable access points"
    )
    parser.add_argument(
        "--sensitivity", action="store_true", help="write radiance-threshold sensitivity tables"
    )
    args = parser.parse_args()

    load_dotenv(APP_DIR / ".env")
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    run_all(
        RunOptions(
            output_dir=args.output_dir,
            threshold=args.threshold,
            osm_pbf=args.osm_pbf,
            access_points=not args.skip_access_points,
            sensitivity=args.sensitivity,
        )
    )


if __name__ == "__main__":
    main()
