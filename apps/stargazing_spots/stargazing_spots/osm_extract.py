"""Candidate features: OSM nodes with a selected tag inside the Portugal land boundary.

Read from the local extract (``make download-osm``), clipped to the boundary built
from the same extract (``make boundary``). All tags are kept; ``@id``/``id`` is "node/<id>".

Usage:
    python -m stargazing_spots.osm_extract -o features.geojson
"""

import argparse
import logging
from pathlib import Path

import geopandas as gpd
import osmium
from shapely.geometry import Point
from shapely.prepared import prep

from stargazing_spots.config import BOUNDARY, OSM_PBF
from stargazing_spots.enrichment import DEFAULT_OSM_TAGS

logger = logging.getLogger(__name__)


def matches(tags: dict[str, str], selection: dict[str, list[str]] = DEFAULT_OSM_TAGS) -> bool:
    """True if any key=value of ``selection`` is present in ``tags``."""
    return any(tags.get(key) in values for key, values in selection.items())


def extract_features_from_pbf(
    pbf_path: Path = OSM_PBF,
    boundary_path: Path = BOUNDARY,
    selection: dict[str, list[str]] = DEFAULT_OSM_TAGS,
) -> tuple[gpd.GeoDataFrame, str]:
    """Matching nodes (EPSG:4326) and the extract's replication timestamp."""
    inside = prep(gpd.read_file(boundary_path).to_crs("EPSG:4326").union_all())
    rows, geoms = [], []
    fp = osmium.FileProcessor(str(pbf_path), osmium.osm.NODE).with_filter(
        osmium.filter.KeyFilter(*selection)
    )
    timestamp = fp.header.get("osmosis_replication_timestamp", "")
    for node in fp:
        if not isinstance(node, osmium.osm.Node):
            continue
        tags = dict(node.tags)
        point = Point(node.location.lon, node.location.lat)
        if matches(tags, selection) and inside.contains(point):
            ref = f"node/{node.id}"
            rows.append({"@id": ref, "id": ref, **tags})
            geoms.append(point)
    logger.info("%d candidate features from %s (%s)", len(rows), pbf_path.name, timestamp)
    return gpd.GeoDataFrame(rows, geometry=geoms, crs="EPSG:4326"), timestamp


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--osm-pbf", type=Path, default=OSM_PBF)
    parser.add_argument("--boundary", type=Path, default=BOUNDARY)
    parser.add_argument("-o", "--output", type=Path, required=True, help="GeoJSON to write")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    features, _ = extract_features_from_pbf(args.osm_pbf, args.boundary)
    features.to_file(args.output, driver="GeoJSON")


if __name__ == "__main__":
    main()
