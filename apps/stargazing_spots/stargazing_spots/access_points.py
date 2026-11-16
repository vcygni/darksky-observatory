"""Drivable access points for dark-sky spots.

Most candidate spots are OSM summits (natural=peak): good for the sky, but the
coordinates often sit on a hilltop away from any road. For each spot this module
finds the nearest point on a road a car can legally use and stop on (see
``is_drivable``) and keeps the spot only if that road point is within
``MAX_WALK_M``.

``MAX_WALK_M`` is measured, not chosen: it is the largest distance between an
official stargazing observation point in Portugal and its nearest drivable road
(validation/portugal/official_observation_points.csv). Spots farther from a
road than any official site are not offered as drive-to destinations.
Recompute it with ``scripts/derive_access_thresholds.py``.

Roads are read from a local OpenStreetMap extract (``make download-osm``), so
the step needs no online API and is reproducible for a given extract date.

Usage:
    python -m stargazing_spots.access_points output/portugal/spots_all.geojson
"""

import argparse
import itertools
import json
import logging
import math
import re
import time
from collections import defaultdict
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import osmium
import rasterio

from stargazing_spots.config import OSM_PBF
from stargazing_spots.tiles import dem_tile

logger = logging.getLogger(__name__)

# Largest road distance among the 18 official observation points (OP07 Posto de
# Vigia de Monte Redondo, Arganil), OSM extract 2026-10-06, drivable roads as
# defined below. Output of scripts/derive_access_thresholds.py.
MAX_WALK_M = 358

# Routability follows the OSRM car profile, the same engine that computes the
# guide's drive times: Project-OSRM/osrm-backend profiles/car.lua and
# profiles/lib/{way_handlers,access,measure}.lua at commit 214ba8f (2026-09-27).
# Two additions are not routing questions but legal ones, and are applied on top:
#   * Stopping: Código da Estrada art. 72.º n.º 2 b) forbids stopping or parking on
#     motorways and their accesses "ainda que fora das faixas de rodagem, salvo nos
#     locais especialmente destinados a esse fim"; art. 75.º extends this to vias
#     reservadas a automóveis e motociclos (OSM motorroad=yes). Text as amended by
#     Lei n.º 72/2013.
#   * Public access: OSRM still routes "restricted" values (private, customers,
#     ...) for trips that start or end there. A guide sends the general public, so
#     of OSRM's restricted values only `destination` (local traffic to that place,
#     OSM wiki Key:access) is accepted.

# car.lua `speeds.highway`: highway types routable by car.
OSRM_HIGHWAY_SPEEDS = {
    "motorway",
    "motorway_link",
    "trunk",
    "trunk_link",
    "primary",
    "primary_link",
    "secondary",
    "secondary_link",
    "tertiary",
    "tertiary_link",
    "unclassified",
    "residential",
    "living_street",
    "service",
    "winter_road",
    "ice_road",
}
# car.lua `access_tags_hierarchy`, most specific first.
OSRM_ACCESS_HIERARCHY = ("motorcar", "motor_vehicle", "vehicle", "access")
# car.lua `access_tag_whitelist` / `access_tag_blacklist`.
OSRM_ACCESS_WHITELIST = {
    "yes",
    "motorcar",
    "motor_vehicle",
    "vehicle",
    "permissive",
    "designated",
    "hov",
}
OSRM_ACCESS_BLACKLIST = {
    "no",
    "agricultural",
    "forestry",
    "emergency",
    "psv",
    "taxi",
    "share_taxi",
    "minibus",
    "bus",
    "foot",
    "emergency_vehicle",
    "restricted",
    "military",
    "official",
    "customers",
    "private",
    "delivery",
    "destination",
    "permit",
    "residents",
}
# car.lua `restricted_access_tag_list` (lower priority than whitelist in resolve_access).
OSRM_ACCESS_RESTRICTED = {
    "private",
    "delivery",
    "destination",
    "customers",
    "permit",
    "residents",
    "unknown",
}
PUBLIC_RESTRICTED_OK = {"destination"}
# car.lua `avoid` entries checked against highway=* (WayHandlers.avoid_ways).
OSRM_AVOID_HIGHWAYS = {"steps", "construction", "proposed"}
OSRM_CONSTRUCTION_WHITELIST = {"no", "widening", "minor"}
OSRM_SERVICE_FORBIDDEN = {"emergency_access"}
# car.lua vehicle dimensions (WayHandlers.handle_height/width/length/weight).
OSRM_VEHICLE = {"height": 2.0, "width": 1.9, "length": 4.8, "weight_kg": 2000}
# Código da Estrada art. 72.º/75.º: no stopping.
NO_STOPPING_HIGHWAYS = {"motorway", "motorway_link"}


@dataclass(frozen=True, slots=True)
class Road:
    osm_id: int
    highway: str
    name: str
    coords: tuple[tuple[float, float], ...]  # (lat, lon)


@dataclass(frozen=True, slots=True)
class AccessPoint:
    kind: str  # road | none
    lat: float | None
    lon: float | None
    walk_m: int | None  # straight-line distance from the road point to the spot
    road_type: str


def nearest_point_on_road(lat: float, lon: float, road: Road) -> tuple[float, float, float]:
    """Closest point on a road polyline to (lat, lon).

    Uses a local equirectangular projection, accurate to well under a metre at
    the ~1.5 km scale used here.

    Returns:
        (distance_m, lat, lon) of the closest point.
    """
    kx = 111_320.0 * math.cos(math.radians(lat))
    ky = 110_540.0
    best = (math.inf, lat, lon)
    pts = [((p_lon - lon) * kx, (p_lat - lat) * ky) for p_lat, p_lon in road.coords]
    for (ax, ay), (bx, by) in itertools.pairwise(pts):
        dx, dy = bx - ax, by - ay
        seg2 = dx * dx + dy * dy
        t = 0.0 if seg2 == 0 else max(0.0, min(1.0, -(ax * dx + ay * dy) / seg2))
        px, py = ax + t * dx, ay + t * dy
        d = math.hypot(px, py)
        if d < best[0]:
            best = (d, lat + py / ky, lon + px / kx)
    if len(pts) == 1:
        ((ax, ay),) = pts
        best = (math.hypot(ax, ay), road.coords[0][0], road.coords[0][1])
    return best


def nearest_road(
    lat: float, lon: float, roads: list[Road]
) -> tuple[float, float, float, Road | None]:
    """Nearest drivable road point: (distance_m, lat, lon, road)."""
    best: tuple[float, float, float, Road | None] = (math.inf, lat, lon, None)
    for road in roads:
        d, rlat, rlon = nearest_point_on_road(lat, lon, road)
        if d < best[0]:
            best = (d, rlat, rlon, road)
    return best


def _access_value(tags: dict[str, str], suffix: str) -> str | None:
    """OSRM Tags.get_forward_backward_by_set + Access.resolve_access for one direction."""
    value = None
    for key in OSRM_ACCESS_HIERARCHY:
        value = tags.get(key + suffix) or tags.get(key)
        if value:
            break
    if not value or ";" not in value:
        return value

    def priority(v: str) -> int:
        if v in OSRM_ACCESS_WHITELIST:
            return 3
        if v in OSRM_ACCESS_RESTRICTED:
            return 2
        if v in OSRM_ACCESS_BLACKLIST:
            return 1
        return 0

    return max((part.strip() for part in value.split(";")), key=priority)


def _number(value: str | None) -> float | None:
    """OSRM Measure.parse_value_*: first number in the string, comma as decimal mark."""
    if not value:
        return None
    m = re.search(r"\d+\.?\d*", value.replace(",", "."))
    return float(m.group()) if m else None


def _too_small(tags: dict[str, str]) -> bool:
    """OSRM handle_height/width/length/weight for the default car (both directions)."""
    height = _number(tags.get("maxheight:physical") or tags.get("maxheight"))
    if tags.get("maxheight") in ("default", "none", "no-sign", "unsigned"):
        height = None
    width = _number(
        tags.get("maxwidth:physical")
        or tags.get("maxwidth")
        or tags.get("width")
        or tags.get("est_width")
    )
    length = _number(tags.get("maxlength"))
    weight = _number(tags.get("maxweightrating") or tags.get("maxweight"))
    if (
        weight is not None
        and "kg" not in (tags.get("maxweight") or "")
        and "lbs" not in (tags.get("maxweight") or "")
    ):
        weight *= 1000  # OSM default unit is metric tonnes
    return (
        (height is not None and height < OSRM_VEHICLE["height"])
        or (width is not None and width <= OSRM_VEHICLE["width"])
        or (length is not None and length < OSRM_VEHICLE["length"])
        or (weight is not None and weight < OSRM_VEHICLE["weight_kg"])
    )


def _blocked(tags: dict[str, str], hw: str) -> bool:
    """OSRM blocked_ways, avoid_ways, vehicle dimensions, service and smoothness."""
    construction = tags.get("construction")
    return (
        tags.get("area") == "yes"
        or tags.get("oneway") == "reversible"
        or tags.get("impassable") == "yes"
        or tags.get("status") == "impassable"
        or bool(construction and construction not in OSRM_CONSTRUCTION_WHITELIST)
        or hw in OSRM_AVOID_HIGHWAYS
        or _too_small(tags)
        or tags.get("service") in OSRM_SERVICE_FORBIDDEN
        or tags.get("smoothness") == "impassable"  # smoothness_speeds: 0 km/h
    )


def _direction_ok(tags: dict[str, str], hw: str, suffix: str) -> bool:
    """OSRM access and speed handling for one direction (":forward" or ":backward")."""
    access = _access_value(tags, suffix)
    # OSRM routes restricted values only on its restricted_highway_whitelist,
    # which equals the speed table.
    restricted_ok = hw in OSRM_HIGHWAY_SPEEDS and access in PUBLIC_RESTRICTED_OK
    if access in OSRM_ACCESS_BLACKLIST and not restricted_ok:
        return False
    if hw in OSRM_HIGHWAY_SPEEDS:
        return True
    # No speed for this highway type: OSRM uses default_speed only with a
    # non-blacklisted access tag (e.g. highway=track + motor_vehicle=yes).
    return access is not None and access not in OSRM_ACCESS_BLACKLIST


def is_drivable(tags: dict[str, str]) -> bool:
    """True if a car can legally drive on this way and stop on it.

    Mirrors OSRM car.lua process_way for the default car, then applies the
    public-access and no-stopping rules described above.
    """
    hw = tags.get("highway")
    if not hw or _blocked(tags, hw):
        return False
    if not (_direction_ok(tags, hw, ":forward") or _direction_ok(tags, hw, ":backward")):
        return False
    # Código da Estrada art. 72.º n.º 2 b) and art. 75.º
    return hw not in NO_STOPPING_HIGHWAYS and tags.get("motorroad") != "yes"


def choose_access_point(
    spot_lat: float, spot_lon: float, roads: list[Road], max_walk_m: float = MAX_WALK_M
) -> AccessPoint:
    """Nearest drivable road point, or kind "none" if it is beyond ``max_walk_m``."""
    d, lat, lon, road = nearest_road(spot_lat, spot_lon, roads)
    if road is None or d > max_walk_m:
        return AccessPoint("none", None, None, None, "")
    return AccessPoint("road", lat, lon, round(d), road.highway)


GRID_DEG = 0.02  # ~2 km cells for the coarse "near any spot" spatial filter


def grid_cells(lat0: float, lat1: float, lon0: float, lon1: float) -> Iterator[tuple[int, int]]:
    """Grid cells overlapped by a lat/lon box."""
    for i in range(math.floor(lat0 / GRID_DEG), math.floor(lat1 / GRID_DEG) + 1):
        for j in range(math.floor(lon0 / GRID_DEG), math.floor(lon1 / GRID_DEG) + 1):
            yield (i, j)


def padded_box(lat: float, lon: float, pad_m: float) -> tuple[float, float, float, float]:
    dlat = pad_m / 110_540.0
    dlon = pad_m / (111_320.0 * math.cos(math.radians(lat)))
    return lat - dlat, lat + dlat, lon - dlon, lon + dlon


def _box(coords: list[tuple[float, float]]) -> tuple[float, float, float, float]:
    lats = [c[0] for c in coords]
    lons = [c[1] for c in coords]
    return min(lats), max(lats), min(lons), max(lons)


def _way_coords(way: osmium.osm.Way) -> list[tuple[float, float]]:
    return [(n.lat, n.lon) for n in way.nodes if n.location.valid()]


def load_roads(
    pbf_path: Path, spots: list[tuple[float, float]], reach_m: float = MAX_WALK_M
) -> tuple[list[Road], str]:
    """Drivable roads passing within ``reach_m`` (grid-approximated) of any spot.

    Returns the roads and the extract's replication timestamp.
    """
    near: set[tuple[int, int]] = set()
    for lat, lon in spots:
        near.update(grid_cells(*padded_box(lat, lon, reach_m)))

    roads: list[Road] = []
    fp = (
        osmium.FileProcessor(str(pbf_path), osmium.osm.NODE | osmium.osm.WAY)
        .with_locations()
        .with_filter(osmium.filter.EntityFilter(osmium.osm.WAY))
        .with_filter(osmium.filter.KeyFilter("highway"))
    )
    timestamp = fp.header.get("osmosis_replication_timestamp", "")
    for way in fp:
        if not isinstance(way, osmium.osm.Way):
            continue
        tags = dict(way.tags)
        if not is_drivable(tags):
            continue
        coords = _way_coords(way)
        if coords and any(c in near for c in grid_cells(*_box(coords))):
            roads.append(Road(way.id, tags["highway"], tags.get("name", ""), tuple(coords)))
    return roads, timestamp


def _elevation(
    lat: float, lon: float, cache: dict[tuple[int, int], rasterio.DatasetReader | None]
) -> float | None:
    """Copernicus GLO-30 elevation, None if the tile is unavailable."""
    key = (math.floor(lat), math.floor(lon))
    if key not in cache:
        try:
            cache[key] = rasterio.open(dem_tile(*key))
        except rasterio.errors.RasterioIOError:
            cache[key] = None
    src = cache[key]
    if src is None:
        return None
    row, col = src.index(lon, lat)
    return float(src.read(1, window=((row, row + 1), (col, col + 1)))[0, 0])


def add_access_points(
    geojson: dict[str, Any], pbf_path: Path, max_walk_m: float = MAX_WALK_M
) -> dict[str, Any]:
    """Add access_* properties to every feature of a spots FeatureCollection."""
    features = geojson["features"]
    spots = [(f["geometry"]["coordinates"][1], f["geometry"]["coordinates"][0]) for f in features]

    logger.info("Reading drivable roads from %s ...", pbf_path.name)
    t0 = time.perf_counter()
    roads, osm_timestamp = load_roads(pbf_path, spots, max_walk_m)
    logger.info("  %d drivable roads near spots (%.0fs)", len(roads), time.perf_counter() - t0)

    road_index: dict[tuple[int, int], list[int]] = defaultdict(list)
    for k, road in enumerate(roads):
        for cell in grid_cells(*_box(list(road.coords))):
            road_index[cell].append(k)

    dem_cache: dict[tuple[int, int], rasterio.DatasetReader | None] = {}
    for f, (lat, lon) in zip(features, spots, strict=True):
        cells = grid_cells(*padded_box(lat, lon, max_walk_m))
        near_roads = [roads[k] for k in {k for c in cells for k in road_index.get(c, ())}]
        ap = choose_access_point(lat, lon, near_roads, max_walk_m)
        climb = None
        if ap.lat is not None and ap.lon is not None:
            z_spot, z_road = _elevation(lat, lon, dem_cache), _elevation(ap.lat, ap.lon, dem_cache)
            if z_spot is not None and z_road is not None:
                climb = round(z_spot - z_road)
        f["properties"].update(
            {
                "access_kind": ap.kind,
                "access_lat": round(ap.lat, 7) if ap.lat is not None else None,
                "access_lon": round(ap.lon, 7) if ap.lon is not None else None,
                "access_walk_m": ap.walk_m,
                "access_climb_m": climb,
                "access_road_type": ap.road_type,
            }
        )

    geojson.setdefault("processing", {})["access_points"] = {
        "max_walk_m": max_walk_m,
        "max_walk_source": "validation/portugal/official_observation_points.csv",
        "drivable_definition": (
            "OSRM car.lua @214ba8f + Codigo da Estrada art. 72/75 + public access"
        ),
        "source": f"OpenStreetMap extract {pbf_path.name}",
        "osm_timestamp": osm_timestamp,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    return geojson


def summarize(geojson: dict[str, Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for f in geojson["features"]:
        k = f["properties"].get("access_kind", "missing")
        counts[k] = counts.get(k, 0) + 1
    return counts


def enrich_geojson_file(path: Path, pbf_path: Path, output: Path | None = None) -> dict[str, int]:
    """Add access points to a spots GeoJSON file in place (or to ``output``)."""
    geojson = json.loads(path.read_text())
    add_access_points(geojson, pbf_path)
    (output or path).write_text(json.dumps(geojson, ensure_ascii=False))
    counts = summarize(geojson)
    logger.info("Access kinds: %s", counts)
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "geojson", type=Path, help="spots GeoJSON to enrich (e.g. spots_all.geojson)"
    )
    parser.add_argument("-o", "--output", type=Path, help="output path (default: overwrite input)")
    parser.add_argument(
        "--osm-pbf", type=Path, default=OSM_PBF, help="OpenStreetMap .osm.pbf extract"
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    enrich_geojson_file(args.geojson, args.osm_pbf, args.output)
    logger.info("Wrote %s", args.output or args.geojson)


if __name__ == "__main__":
    main()
