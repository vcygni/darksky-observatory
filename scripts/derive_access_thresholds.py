"""Derive MAX_WALK_M for the access-point step from ground-truth observation points.

For every official observation point in
validation/portugal/official_observation_points.csv, measure the distance to the
nearest drivable road (stargazing_spots.access_points.is_drivable) in the local
OpenStreetMap extract. MAX_WALK_M is the largest of these distances: no official
site in Portugal is farther from a drivable road.

Usage:
    uv run python scripts/derive_access_thresholds.py
"""

import csv
import statistics
from pathlib import Path

from stargazing_spots.access_points import MAX_WALK_M, load_roads, nearest_road
from stargazing_spots.config import OSM_PBF

ROOT = Path(__file__).resolve().parent.parent

GROUND_TRUTH = ROOT / "validation" / "portugal" / "official_observation_points.csv"
# Search well beyond any plausible threshold so the measurement is not truncated.
MEASURE_REACH_M = 5000


def main() -> None:
    points = list(csv.DictReader(GROUND_TRUTH.open(encoding="utf-8")))
    coords = [(float(p["lat"]), float(p["lon"])) for p in points]
    roads, timestamp = load_roads(OSM_PBF, coords, MEASURE_REACH_M)

    rows = []
    for p, (lat, lon) in zip(points, coords, strict=True):
        d, _, _, road = nearest_road(lat, lon, roads)
        rows.append(
            (
                p["id"],
                p["name"],
                p["confidence"],
                round(d),
                road.highway if road else "",
            )
        )

    print(f"OSM extract: {OSM_PBF.name} ({timestamp})")
    print(f"Ground truth: {GROUND_TRUTH.relative_to(ROOT)} ({len(rows)} points)\n")
    for pid, name, conf, d, hw in sorted(rows, key=lambda r: r[3]):
        print(f"  {pid}  {name[:45]:45} {conf:6}  {d:5d} m  {hw}")

    dists = [r[3] for r in rows]
    high = [r[3] for r in rows if r[2] == "high"]
    print(f"\nmedian {statistics.median(dists):.0f} m | max (all) {max(dists)} m")
    print(f"max (high confidence) {max(high)} m")
    print(f"MAX_WALK_M in access_points.py: {MAX_WALK_M} m")
    if max(dists) != MAX_WALK_M:
        print(f"-> update MAX_WALK_M to {max(dists)}")


if __name__ == "__main__":
    main()
