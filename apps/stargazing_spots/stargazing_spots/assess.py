"""Multi-criteria assessment of candidate spots, selection and spatial thinning."""

import logging

import geopandas as gpd
import numpy as np
import numpy.typing as npt
from scipy.spatial import cKDTree

from stargazing_spots.access_check import assess_access
from stargazing_spots.cloud_cover import compute_clear_night_fraction, resample_to_viirs_grid
from stargazing_spots.config import RegionName
from stargazing_spots.geo import FloatArray, sample
from stargazing_spots.land_cover import (
    LAND_COVER_CLASSES,
    REMOVED_CLASSES,
    canopy_fraction,
    land_cover_at_points,
)
from stargazing_spots.skyglow import assess_spots as add_skyglow
from stargazing_spots.suitability import compute_ssi
from stargazing_spots.terrain import classify_slope, terrain_at_points

logger = logging.getLogger(__name__)

MIN_SVF = 0.7  # design choice
DEDUP_RADIUS_M = 1000  # design choice: one recommendation per ~1 km
DENSITY_CELL_DEG = 0.25  # design choice: ~25 km cells
DENSITY_MAX_PER_CELL = 5
DENSITY_MIN_SPOTS = 100  # the cap applies only above this many spots (design choice)
UTM_29N = 32629
MIN_SPLIT_VALUES = 2

DESTINATION_TAGS = {
    "tourism": ("viewpoint", "camp_site", "picnic_site", "wilderness_hut"),
    "amenity": ("shelter",),
    "man_made": ("observatory",),
    "leisure": ("nature_reserve", "bird_hide"),
}


def assess(
    spots: gpd.GeoDataFrame,
    radiance: FloatArray,
    x: FloatArray,
    y: FloatArray,
    region: RegionName,
) -> gpd.GeoDataFrame:
    """Add sky brightness, cloud, terrain, land cover, access and SSI columns."""
    spots = add_skyglow(spots, radiance, x, y)
    lon, lat = spots.geometry.x.values, spots.geometry.y.values

    clear = resample_to_viirs_grid(compute_clear_night_fraction(region=region), x, y)
    terrain = terrain_at_points(lon, lat)
    canopy = canopy_fraction(lon, lat)
    classes, land_scores = land_cover_at_points(lon, lat, canopy)
    slope = [classify_slope(s) for s in terrain.slope_deg]

    spots = spots.assign(
        clear_night_fraction=np.round(sample(clear, x, y, lon, lat), 3),
        sky_view_factor=np.round(terrain.svf * (1 - canopy), 3),
        dem_elevation_m=np.round(terrain.elevation_m, 0),
        ele=terrain.elevation_m,
        land_cover_class=classes,
        land_cover_label=[LAND_COVER_CLASSES.get(int(c), "unknown") for c in classes],
        land_cover_score=land_scores,
        terrain_slope_deg=np.round(terrain.slope_deg, 1),
        slope_score=[s for s, _ in slope],
        slope_class=[label for _, label in slope],
    )
    return compute_ssi(assess_access(spots))


def two_class_split(values: npt.ArrayLike) -> float:
    """Threshold with maximum between-class variance (Otsu 1979; two-class Jenks).

    Returns the midpoint between the last value of the lower class and the first
    of the upper class.
    """
    v = np.sort(np.asarray(values, dtype=np.float64))
    v = v[~np.isnan(v)]
    n = len(v)
    if n < MIN_SPLIT_VALUES or v[0] == v[-1]:
        return float(v[0]) if n else float("nan")
    k = np.arange(1, n)
    csum = np.cumsum(v)
    m0 = csum[:-1] / k
    m1 = (csum[-1] - csum[:-1]) / (n - k)
    between = (k / n) * ((n - k) / n) * (m0 - m1) ** 2
    between[v[1:] == v[:-1]] = -1  # a split must fall between distinct values
    i = int(np.argmax(between))
    return float((v[i] + v[i + 1]) / 2)


def ssi_percentile(values: npt.ArrayLike, reference: npt.ArrayLike) -> FloatArray:
    """Share of ``reference`` values that are <= each value (0-1)."""
    ref = np.sort(np.asarray(reference, dtype=np.float64))
    position = np.searchsorted(ref, np.asarray(values, dtype=np.float64), side="right")
    return position / max(len(ref), 1)


def filter_physical(spots: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Drop obstructed sky, built-up/water land cover and night-restricted access."""
    return spots[
        ~(spots["sky_view_factor"] < MIN_SVF)
        & ~spots["land_cover_class"].isin(REMOVED_CLASSES)
        & spots["night_accessible"].astype(bool)
    ]


def select_spots(spots: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Physical filters, upper class of the region's two-class SSI split, tier, thinning.

    The split is computed per call (one region), so each region is ranked against
    its own climate. Keeping the upper class is a design choice.
    """
    spots = filter_physical(spots)
    split = two_class_split(spots["ssi_score"])
    spots = spots.assign(
        ssi_percentile=np.round(ssi_percentile(spots["ssi_score"], spots["ssi_score"]), 3)
    )
    spots = spots[spots["ssi_score"] >= split]  # also drops missing SSI
    logger.info("SSI split %.1f: %d spots", split, len(spots))

    is_destination = np.zeros(len(spots), dtype=bool)
    for key, values in DESTINATION_TAGS.items():
        if key in spots.columns:
            is_destination |= spots[key].isin(values).to_numpy()
    spots = spots.assign(tier=np.where(is_destination, "destination", "candidate"))
    return thin_spatially(spots).reset_index(drop=True)


def _rank_order(spots: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """SSI descending, ties by OSM id, so the order never depends on input order."""
    tiebreak = spots["id"].astype(str) if "id" in spots.columns else spots.index.astype(str)
    return (
        spots.assign(_tiebreak=tiebreak)
        .sort_values(["ssi_score", "_tiebreak"], ascending=[False, True], kind="mergesort")
        .drop(columns="_tiebreak")
    )


def thin_spatially(spots: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Best-first deduplication, then a per-cell cap on a fixed grid.

    Spots within DEDUP_RADIUS_M of a better one are dropped; then at most
    DENSITY_MAX_PER_CELL remain per DENSITY_CELL_DEG cell. The result depends only
    on the set of spots, not their order.
    """
    if len(spots) <= 1:
        return spots
    ranked = _rank_order(spots).reset_index(drop=True)
    utm = ranked.to_crs(epsg=UTM_29N)
    coords = np.column_stack([utm.geometry.x, utm.geometry.y])
    tree = cKDTree(coords)
    suppressed = np.zeros(len(ranked), dtype=bool)
    keep = []
    for i in range(len(ranked)):
        if not suppressed[i]:
            keep.append(i)
            suppressed[tree.query_ball_point(coords[i], r=DEDUP_RADIUS_M)] = True
    ranked = ranked.iloc[keep]

    if len(ranked) > DENSITY_MIN_SPOTS:
        cell_y = np.floor(ranked.geometry.y / DENSITY_CELL_DEG).astype(int)
        cell_x = np.floor(ranked.geometry.x / DENSITY_CELL_DEG).astype(int)
        ranked = ranked.groupby([cell_y, cell_x], sort=False).head(DENSITY_MAX_PER_CELL)
    return ranked
