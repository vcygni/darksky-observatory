"""STAC catalog describing one region's outputs."""

from datetime import UTC, datetime
from pathlib import Path

import pystac

from stargazing_spots import __version__
from stargazing_spots.config import YEARS, BBox

SOURCE_URL = "https://ladsweb.modaps.eosdis.nasa.gov/missions-and-measurements/products/VNP46A4"


def create_darksky_catalog(
    output_dir: Path,
    region: str,
    bbox: BBox,
    spots_geojson: Path,
    darksky_cog: Path,
    n_spots: int,
    threshold: float,
) -> None:
    """Self-contained catalog: one collection, one item with the spots and dark-sky raster."""
    start = datetime(int(YEARS[0]), 1, 1, tzinfo=UTC)
    end = datetime(int(YEARS[-1]), 12, 31, tzinfo=UTC)
    west, south, east, north = bbox

    catalog = pystac.Catalog(
        id="darksky-observatory",
        description="Stargazing spots ranked from VIIRS radiance, terrain and cloud climatology.",
    )
    collection = pystac.Collection(
        id=f"darksky-{region}",
        description=f"Dark-sky pixels and ranked spots, {region}, VIIRS VNP46A4 annual composites.",
        extent=pystac.Extent(
            pystac.SpatialExtent([list(bbox)]), pystac.TemporalExtent([[start, end]])
        ),
        license="Apache-2.0",
    )
    collection.add_link(pystac.Link(rel="derived_from", target=SOURCE_URL, title="NASA VNP46A4"))

    item = pystac.Item(
        id=f"darksky-{region}-{YEARS[0]}-{YEARS[-1]}",
        geometry={
            "type": "Polygon",
            "coordinates": [
                [[west, south], [east, south], [east, north], [west, north], [west, south]]
            ],
        },
        bbox=list(bbox),
        datetime=None,
        start_datetime=start,
        end_datetime=end,
        properties={
            "processing:software": {"stargazing-spots": __version__},
            "darksky:threshold_nw_cm2_sr": threshold,
            "darksky:spots": n_spots,
            "instruments": ["viirs"],
            "platform": "suomi-npp",
        },
    )
    item.add_asset(
        "spots",
        pystac.Asset(str(spots_geojson), media_type=pystac.MediaType.GEOJSON, roles=["data"]),
    )
    item.add_asset(
        "dark_sky",
        pystac.Asset(str(darksky_cog), media_type=pystac.MediaType.COG, roles=["data"]),
    )
    collection.add_item(item)
    catalog.add_child(collection)
    catalog.normalize_hrefs(str(output_dir))
    catalog.save(catalog_type=pystac.CatalogType.SELF_CONTAINED)
