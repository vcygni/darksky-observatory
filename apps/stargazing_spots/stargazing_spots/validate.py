"""Validation of the predicted SQM map (docs/methodology.md, Validation Summary).

* TESS photometers (primary): clear-sky moonless zenith SQM per site from
  scripts/derive_tess_clear_sky.py; sites in one model pixel are averaged.
* Published SQM sites (indicative): rows marked "indicative" in
  validation/portugal/published_sites_audit.csv, reported separately.
* Official observation points (descriptive): distance to the nearest spot.

Points outside the raster are not sampled. No error is pooled across sources.
"""

import json
import logging
import os
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import numpy.typing as npt
import pandas as pd
from scipy.spatial import cKDTree
from scipy.stats import pearsonr, spearmanr
from shapely import wkt

from stargazing_spots.geo import FloatArray, inside, nearest_index

logger = logging.getLogger(__name__)

UTM_29N = 32629
MIN_CORRELATION_POINTS = 3


def find_validation_dir() -> Path:
    """$VALIDATION_DIR, else the nearest parent directory containing validation/portugal."""
    env = os.getenv("VALIDATION_DIR")
    if env:
        return Path(env)
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "validation" / "portugal"
        if candidate.is_dir():
            return candidate
    return here.parent / "validation" / "portugal"  # absent: loaders return None


VALIDATION_DIR = find_validation_dir()


def load_published_sites() -> gpd.GeoDataFrame | None:
    """Measured published sites joined with their audit decision."""
    csv_path = VALIDATION_DIR / "stargazing_sites.csv"
    audit_path = VALIDATION_DIR / "published_sites_audit.csv"
    if not csv_path.exists() or not audit_path.exists():
        return None
    sites = pd.read_csv(csv_path)
    measured = sites[sites["sqm_type"] == "measured"].merge(
        pd.read_csv(audit_path), on="name", how="left", validate="one_to_one"
    )
    if measured["use"].isna().any():
        missing = measured.loc[measured["use"].isna(), "name"].tolist()
        raise ValueError(f"Measured sites without an audit decision: {missing}")
    measured["geometry"] = measured["WKT"].apply(wkt.loads)
    return gpd.GeoDataFrame(measured, geometry="geometry", crs="EPSG:4326")


def load_tess_sites() -> list[dict[str, Any]] | None:
    path = VALIDATION_DIR / "tess-ida" / "tess_clear_sky.json"
    if not path.exists():
        return None
    data = json.loads(path.read_text())
    return [s for s in data["sites"] if "clear_sky_sqm_mode" in s]


def load_official_points() -> gpd.GeoDataFrame | None:
    path = VALIDATION_DIR / "official_observation_points.csv"
    if not path.exists():
        return None
    pts = pd.read_csv(path)
    return gpd.GeoDataFrame(
        pts, geometry=gpd.points_from_xy(pts["lon"], pts["lat"]), crs="EPSG:4326"
    )


def pixel_index(
    x_coords: FloatArray, y_coords: FloatArray, lat: float, lon: float
) -> tuple[int, int] | None:
    """Row/col of the model pixel containing (lat, lon), or None if outside the raster."""
    if not (inside(x_coords, [lon])[0] and inside(y_coords, [lat])[0]):
        return None
    return int(nearest_index(y_coords, [lat])[0]), int(nearest_index(x_coords, [lon])[0])


def sample_sqm_map(
    sqm_map: FloatArray, x_coords: FloatArray, y_coords: FloatArray, lat: float, lon: float
) -> float:
    """Predicted SQM at a coordinate; NaN outside the raster or on nodata."""
    idx = pixel_index(x_coords, y_coords, lat, lon)
    if idx is None:
        return np.nan
    return float(sqm_map[idx])


def metrics(pred: npt.ArrayLike, obs: npt.ArrayLike) -> dict[str, float | int]:
    pred, obs = np.asarray(pred, float), np.asarray(obs, float)
    err = pred - obs
    out = {
        "n": len(err),
        "mae": round(float(np.mean(np.abs(err))), 3),
        "bias": round(float(np.mean(err)), 3),
        "rmse": round(float(np.sqrt(np.mean(err**2))), 3),
        "max_abs_error": round(float(np.max(np.abs(err))), 3),
    }
    if len(err) >= MIN_CORRELATION_POINTS:
        out["pearson_r"] = round(float(pearsonr(pred, obs).statistic), 3)
        out["spearman_rho"] = round(float(spearmanr(pred, obs).statistic), 3)
    return out


def group_tess_by_pixel(
    tess: list[dict[str, Any]], sqm_map: np.ndarray, x_coords: np.ndarray, y_coords: np.ndarray
) -> tuple[dict[tuple[int, int], list[dict[str, Any]]], list[str]]:
    """TESS sites keyed by model pixel, plus stations outside the raster or on nodata.

    Sites in one pixel are averaged downstream so a location is not counted twice.
    Shared by validation and scripts/fit_calibration.py so both use the same sample.
    """
    by_pixel: dict[tuple[int, int], list[dict[str, Any]]] = {}
    outside = []
    for s in tess:
        idx = pixel_index(x_coords, y_coords, s["lat"], s["lon"])
        if idx is None or np.isnan(sqm_map[idx]):
            outside.append(s["station"])
            continue
        by_pixel.setdefault(idx, []).append(s)
    return by_pixel, outside


def run_validation(
    sqm_map: np.ndarray,
    x_coords: np.ndarray,
    y_coords: np.ndarray,
    spots: gpd.GeoDataFrame | None = None,
) -> dict[str, Any]:
    """Validate the predicted SQM map; see module docstring for source handling."""
    report: dict[str, Any] = {"primary": {}, "indicative": {}, "descriptive": {}}

    # 1. TESS (primary)
    tess = load_tess_sites()
    if tess:
        by_pixel, outside = group_tess_by_pixel(tess, sqm_map, x_coords, y_coords)
        rows = []
        for idx, sites in sorted(by_pixel.items()):
            rows.append(
                {
                    "stations": sorted({s["station"] for s in sites}),
                    "location": sites[0]["location"],
                    "lat": sites[0]["lat"],
                    "lon": sites[0]["lon"],
                    "country": sites[0]["location"].rsplit("/", 1)[-1].strip(),
                    "nights": int(sum(s["nights_dark_moonless"] for s in sites)),
                    "observed_mode": round(
                        float(np.mean([s["clear_sky_sqm_mode"] for s in sites])), 3
                    ),
                    "observed_median": round(float(np.mean([s["sqm_median"] for s in sites])), 3),
                    "predicted": round(float(sqm_map[idx]), 3),
                }
            )
        if rows:
            report["primary"]["tess_clear_sky"] = {
                **metrics([r["predicted"] for r in rows], [r["observed_mode"] for r in rows]),
                "sensitivity_vs_median": metrics(
                    [r["predicted"] for r in rows], [r["observed_median"] for r in rows]
                ),
                "excluded_outside_raster": outside,
                "sites": rows,
                "description": (
                    "TESS clear-sky moonless zenith SQM (KDE mode), one value per model pixel"
                ),
            }
            logger.info(
                "TESS clear-sky: MAE=%.3f bias=%+.3f r=%s (%d pixels; %d outside raster)",
                report["primary"]["tess_clear_sky"]["mae"],
                report["primary"]["tess_clear_sky"]["bias"],
                report["primary"]["tess_clear_sky"].get("pearson_r"),
                len(rows),
                len(outside),
            )

    # 2. Published sites (indicative only, per audit)
    published = load_published_sites()
    if published is not None:
        used = published[published["use"] == "indicative"]
        pred = [sample_sqm_map(sqm_map, x_coords, y_coords, g.y, g.x) for g in used.geometry]
        ok = [i for i, p in enumerate(pred) if not np.isnan(p)]
        if ok:
            report["indicative"]["published_sqm"] = {
                **metrics([pred[i] for i in ok], used["expected_sqm"].to_numpy()[ok]),
                "sites": [
                    {
                        "name": used["name"].iloc[i],
                        "expected": float(used["expected_sqm"].iloc[i]),
                        "predicted": round(pred[i], 3),
                    }
                    for i in ok
                ],
                "excluded": dict(
                    zip(
                        published.loc[published["use"] == "excluded", "name"],
                        published.loc[published["use"] == "excluded", "reason"],
                        strict=True,
                    )
                ),
                "description": (
                    "Not a baseline: per-site value/location not verifiable"
                    " (published_sites_audit.csv)"
                ),
            }

    # 3. Official observation points vs pipeline spots (descriptive)
    official = load_official_points()
    if official is not None and spots is not None and len(spots) > 0:
        utm = spots.to_crs(epsg=UTM_29N)
        tree = cKDTree(np.column_stack([utm.geometry.x, utm.geometry.y]))
        o = official.to_crs(epsg=UTM_29N)
        d_km, _ = tree.query(np.column_stack([o.geometry.x, o.geometry.y]))
        d_km = d_km / 1000
        report["descriptive"]["official_points_to_nearest_spot_km"] = {
            "n": len(d_km),
            "median": round(float(np.median(d_km)), 1),
            "max": round(float(d_km.max()), 1),
            "per_point": {
                pid: round(float(d), 1) for pid, d in zip(official["id"], d_km, strict=True)
            },
        }

    report["baseline"] = {
        "metric": "primary.tess_clear_sky.mae",
        "value": report["primary"].get("tess_clear_sky", {}).get("mae"),
        "model_interpretation": (
            "clear-sky moonless zenith brightness (PSF model + 22.0 natural background)"
        ),
    }
    return report


def save_validation_report(report: dict[str, Any], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False))
    logger.info("Validation report saved: %s", output_path)
