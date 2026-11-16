"""Portugal land boundary from the local OpenStreetMap extract.

The country relation (admin_level=2) includes territorial waters, so the land
area is taken as the union of the municipalities (admin_level=7, "concelhos")
whose representative point lies inside the country relation. Mainland,
Madeira and the Azores are all included.

Output: apps/stargazing_spots/input/portugal/boundary/portugal_osm.geojson
(not committed; OpenStreetMap data, ODbL).

Usage:
    cd apps/stargazing_spots
    uv run python ../../scripts/build_boundary.py
"""

import logging
from pathlib import Path

import geopandas as gpd
import osmium
from shapely import wkb
from shapely.ops import unary_union

APP = Path(__file__).resolve().parent.parent / "apps" / "stargazing_spots"
PBF = APP / "input" / "portugal" / "osm" / "portugal-latest.osm.pbf"
OUTPUT = APP / "input" / "portugal" / "boundary" / "portugal_osm.geojson"

logger = logging.getLogger(__name__)


def admin_areas(pbf: Path) -> tuple[list, list]:
    """(country polygons tagged ISO3166-1=PT, municipality polygons)."""
    factory = osmium.geom.WKBFactory()
    country, municipalities = [], []
    fp = osmium.FileProcessor(str(pbf)).with_areas(
        osmium.filter.TagFilter(("boundary", "administrative"))
    )
    for obj in fp:
        if not obj.is_area() or obj.tags.get("boundary") != "administrative":
            continue
        level = obj.tags.get("admin_level")
        if level not in ("2", "7"):
            continue
        try:
            geom = wkb.loads(factory.create_multipolygon(obj), hex=True)
        except RuntimeError:  # incomplete relation at the extract edge
            continue
        if level == "2" and obj.tags.get("ISO3166-1") == "PT":
            country.append(geom)
        elif level == "7":
            municipalities.append((obj.tags.get("name", ""), geom))
    return country, municipalities


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    country, municipalities = admin_areas(PBF)
    if not country:
        raise SystemExit(f"No admin_level=2 ISO3166-1=PT relation in {PBF}")
    pt = unary_union(country)
    kept = [(n, g) for n, g in municipalities if pt.contains(g.representative_point())]
    land = unary_union([g for _, g in kept])
    gdf = gpd.GeoDataFrame(
        {
            "name": ["Portugal"],
            "source": [f"OpenStreetMap ({PBF.name}), admin_level=7 union"],
        },
        geometry=[land],
        crs="EPSG:4326",
    )
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    gdf.to_file(OUTPUT, driver="GeoJSON")
    logger.info("%d municipalities -> %s (bounds %s)", len(kept), OUTPUT, land.bounds)


if __name__ == "__main__":
    main()
