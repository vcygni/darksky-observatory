"""Candidate OSM features from the local OpenStreetMap extract.

Replaces the one-off Overpass export (input/portugal/osm/osm_features_portugal.geojson,
2026-05-04) so that candidate spots and access points come from the same OSM
snapshot (``make download-osm``) and no online API is needed.

Selection is ``enrichment.DEFAULT_OSM_TAGS`` (the same tags ``fetch_osm_features``
queries), nodes only as in the previous export, clipped to the GADM Portugal
boundary. Every OSM tag is kept as a column, plus ``@id``/``id`` = "node/<id>".

Usage:
    python -m stargazing_spots.osm_extract [-o features.geojson]
"""

import argparse
import logging
from pathlib import Path

import geopandas as gpd
import osmium
from shapely.geometry import Point
from shapely.prepared import prep

from stargazing_spots.access_points import DEFAULT_OSM_PBF
from stargazing_spots.enrichment import DEFAULT_OSM_TAGS

logger = logging.getLogger(__name__)

DEFAULT_BOUNDARY = (
    Path(__file__).parent.parent / "input" / "portugal" / "boundary" / "gadm41_PRT_1.json.zip"
)


def matches(tags: dict, selection: dict[str, list[str]] = DEFAULT_OSM_TAGS) -> bool:
    """True if any key=value of ``selection`` is present in ``tags``."""
    return any(tags.get(key) in values for key, values in selection.items())


def extract_features_from_pbf(
    pbf_path: Path = DEFAULT_OSM_PBF,
    boundary_path: Path | None = DEFAULT_BOUNDARY,
    selection: dict[str, list[str]] = DEFAULT_OSM_TAGS,
) -> tuple[gpd.GeoDataFrame, str]:
    """Nodes matching ``selection`` inside the boundary, with all their tags.

    Returns the features (EPSG:4326) and the extract's replication timestamp.
    """
    inside = None
    if boundary_path is not None:
        boundary = gpd.read_file(
            f"zip://{boundary_path}" if boundary_path.suffix == ".zip" else boundary_path
        )
        inside = prep(boundary.to_crs("EPSG:4326").union_all())

    rows, geoms = [], []
    fp = osmium.FileProcessor(str(pbf_path), osmium.osm.NODE).with_filter(
        osmium.filter.KeyFilter(*selection)
    )
    timestamp = fp.header.get("osmosis_replication_timestamp", "")
    for node in fp:
        tags = dict(node.tags)
        if not matches(tags, selection):
            continue
        point = Point(node.location.lon, node.location.lat)
        if inside is not None and not inside.contains(point):
            continue
        ref = f"node/{node.id}"
        rows.append({"@id": ref, "id": ref, **tags})
        geoms.append(point)

    features = gpd.GeoDataFrame(rows, geometry=geoms, crs="EPSG:4326")
    logger.info(
        "Extracted %d candidate features from %s (%s)", len(features), pbf_path.name, timestamp
    )
    return features, timestamp


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--osm-pbf", type=Path, default=DEFAULT_OSM_PBF)
    parser.add_argument("--boundary", type=Path, default=DEFAULT_BOUNDARY)
    parser.add_argument("-o", "--output", type=Path, required=True, help="GeoJSON to write")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    features, _ = extract_features_from_pbf(args.osm_pbf, args.boundary)
    features.to_file(args.output, driver="GeoJSON")
    logger.info("Wrote %s", args.output)


if __name__ == "__main__":
    main()
