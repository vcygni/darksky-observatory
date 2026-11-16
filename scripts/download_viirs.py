"""Download the VNP46A4 annual composites the pipeline reads (``make download-viirs``).

One joblib cache per region and year (config.viirs_cache) from NASA Black Marble,
quality flags 1 (poor) and 255 (fill) removed. Needs EARTHDATA_TOKEN.
"""

import datetime as dt
import logging
import os
import tempfile
from pathlib import Path

import geopandas as gpd
import joblib
from blackmarble.raster import bm_raster
from dotenv import load_dotenv
from shapely.geometry import box

from stargazing_spots.config import (
    APP_DIR,
    REGIONS,
    VIIRS_PRODUCT,
    VIIRS_VARIABLE,
    YEARS,
    viirs_cache,
)

QUALITY_FLAGS_REMOVED = [1, 255]

logger = logging.getLogger(__name__)


def main() -> None:
    load_dotenv(APP_DIR / ".env")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    token = os.environ.get("EARTHDATA_TOKEN")
    if not token:
        raise SystemExit("EARTHDATA_TOKEN is not set (https://urs.earthdata.nasa.gov)")

    for region in REGIONS.values():
        area = gpd.GeoDataFrame(geometry=[box(*region.viirs_bbox)], crs="EPSG:4326")
        for year in YEARS:
            target = viirs_cache(region, year)
            if target.exists():
                continue
            with tempfile.TemporaryDirectory() as tiles:
                dataset = bm_raster(
                    area,
                    product_id=VIIRS_PRODUCT,
                    date_range=dt.date(int(year), 1, 1),
                    token=token,
                    variable=VIIRS_VARIABLE,
                    drop_values_by_quality_flag=QUALITY_FLAGS_REMOVED,
                    output_directory=Path(tiles),
                )
            target.parent.mkdir(parents=True, exist_ok=True)
            joblib.dump(dataset, target)
            logger.info("Wrote %s", target.name)


if __name__ == "__main__":
    main()
