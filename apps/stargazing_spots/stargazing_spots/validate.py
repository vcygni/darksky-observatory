"""Validation of the PSF sky-brightness model against independent ground truth.

Sources and how each is used (see docs/methodology.md §15):

* TESS photometers (primary): clear-sky moonless zenith brightness per site,
  derived from the raw readings by scripts/derive_tess_clear_sky.py (header
  positions, calibrated files only, Sun < -18°, Moon < 0°, KDE mode). Sites
  falling in the same model pixel are averaged so one location is not counted
  twice (e.g. two photometers on one Porto building).
* Published SQM sites: only rows that validation/portugal/published_sites_audit.csv
  marks "indicative" (peer-reviewed source exists, per-site value/location not
  verifiable) are reported, separately; none qualify as primary.
* darkskysites.com grid: a VIIRS-based model, not an observation. Reported as a
  model inter-comparison, never as validation.
* Official observation points: distance from each point to the nearest pipeline
  spot (descriptive; replaces town-centre "expert spots").

Points outside the model raster are never sampled (previously they were clamped
to the edge pixel). No MAE is pooled across heterogeneous sources.
"""

import json
import logging
import os
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from scipy.stats import pearsonr, spearmanr
from shapely import wkt

logger = logging.getLogger(__name__)


def _find_validation_dir() -> Path:
    """Locate validation/portugal: $VALIDATION_DIR, else the nearest parent that has it.

    The repo layout puts it three levels above this file; in the Docker image it
    is mounted at /app/validation, one level up. A fixed ``parents[3]`` raised
    IndexError inside the container.
    """
    env = os.getenv("VALIDATION_DIR")
    if env:
        return Path(env)
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "validation" / "portugal"
        if candidate.is_dir():
            return candidate
    return here.parent / "validation" / "portugal"  # not found; loaders report missing files


VALIDATION_DIR = _find_validation_dir()


# --- Loading ------------------------------------------------------------------


def _load_published_sites() -> gpd.GeoDataFrame | None:
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


def _load_tess_sites() -> list[dict] | None:
    path = VALIDATION_DIR / "tess-ida" / "tess_clear_sky.json"
    if not path.exists():
        return None
    data = json.loads(path.read_text())
    return [s for s in data["sites"] if "clear_sky_sqm_mode" in s]


def _load_darkskysites_grid():
    grid_path = VALIDATION_DIR / "darkskysites" / "portugal_grid_sqm_2012_2025.json"
    if not grid_path.exists():
        return None
    return json.loads(grid_path.read_text())["data"]


def _load_official_points() -> gpd.GeoDataFrame | None:
    path = VALIDATION_DIR / "official_observation_points.csv"
    if not path.exists():
        return None
    pts = pd.read_csv(path)
    return gpd.GeoDataFrame(
        pts, geometry=gpd.points_from_xy(pts["lon"], pts["lat"]), crs="EPSG:4326"
    )


# --- Sampling and statistics ----------------------------------------------------


def _pixel_index(x_coords, y_coords, lat, lon) -> tuple[int, int] | None:
    """Row/col of the model pixel containing (lat, lon), or None if outside the raster."""
    dx = abs(float(x_coords[1] - x_coords[0]))
    dy = abs(float(y_coords[1] - y_coords[0]))
    if not (x_coords.min() - dx / 2 <= lon <= x_coords.max() + dx / 2):
        return None
    if not (y_coords.min() - dy / 2 <= lat <= y_coords.max() + dy / 2):
        return None
    return int(np.argmin(np.abs(y_coords - lat))), int(np.argmin(np.abs(x_coords - lon)))


def _sample_sqm_map(sqm_map, x_coords, y_coords, lat, lon) -> float:
    """Predicted SQM at a coordinate; NaN outside the raster or on nodata."""
    idx = _pixel_index(x_coords, y_coords, lat, lon)
    if idx is None:
        return np.nan
    return float(sqm_map[idx])


def _metrics(pred, obs) -> dict:
    pred, obs = np.asarray(pred, float), np.asarray(obs, float)
    err = pred - obs
    out = {
        "n": int(len(err)),
        "mae": round(float(np.mean(np.abs(err))), 3),
        "bias": round(float(np.mean(err)), 3),
        "rmse": round(float(np.sqrt(np.mean(err**2))), 3),
        "max_abs_error": round(float(np.max(np.abs(err))), 3),
    }
    if len(err) > 2:
        out["pearson_r"] = round(float(pearsonr(pred, obs)[0]), 3)
        out["spearman_rho"] = round(float(spearmanr(pred, obs)[0]), 3)
    return out


def group_tess_by_pixel(
    tess: list[dict], sqm_map: np.ndarray, x_coords: np.ndarray, y_coords: np.ndarray
) -> tuple[dict[tuple[int, int], list[dict]], list[str]]:
    """TESS sites keyed by model pixel, plus stations outside the raster or on nodata.

    Sites in one pixel are averaged downstream so a location is not counted twice.
    Shared by validation and scripts/fit_calibration.py so both use the same sample.
    """
    by_pixel: dict[tuple[int, int], list[dict]] = {}
    outside = []
    for s in tess:
        idx = _pixel_index(x_coords, y_coords, s["lat"], s["lon"])
        if idx is None or np.isnan(sqm_map[idx]):
            outside.append(s["station"])
            continue
        by_pixel.setdefault(idx, []).append(s)
    return by_pixel, outside


# --- Validation ---------------------------------------------------------------------


def run_validation(
    sqm_map: np.ndarray,
    x_coords: np.ndarray,
    y_coords: np.ndarray,
    spots: gpd.GeoDataFrame | None = None,
) -> dict:
    """Validate the predicted SQM map; see module docstring for source handling."""
    report = {"primary": {}, "indicative": {}, "model_intercomparison": {}, "descriptive": {}}

    # 1. TESS (primary)
    tess = _load_tess_sites()
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
                **_metrics([r["predicted"] for r in rows], [r["observed_mode"] for r in rows]),
                "sensitivity_vs_median": _metrics(
                    [r["predicted"] for r in rows], [r["observed_median"] for r in rows]
                ),
                "excluded_outside_raster": outside,
                "sites": rows,
                "description": "TESS clear-sky moonless zenith SQM (KDE mode), one value per model pixel",
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
    published = _load_published_sites()
    if published is not None:
        used = published[published["use"] == "indicative"]
        pred = [_sample_sqm_map(sqm_map, x_coords, y_coords, g.y, g.x) for g in used.geometry]
        ok = [i for i, p in enumerate(pred) if not np.isnan(p)]
        if ok:
            report["indicative"]["published_sqm"] = {
                **_metrics([pred[i] for i in ok], used["expected_sqm"].to_numpy()[ok]),
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
                "description": "Not a baseline: per-site value/location not verifiable (published_sites_audit.csv)",
            }

    # 3. darkskysites.com (model inter-comparison)
    grid = _load_darkskysites_grid()
    if grid:
        preds, refs = [], []
        for pt in grid:
            annual = {r["year"]: r["sqm"] for r in pt["annual"]}
            ref = annual.get(2024, annual.get(2023))
            p = _sample_sqm_map(sqm_map, x_coords, y_coords, pt["lat"], pt["lon"])
            if ref is not None and not np.isnan(p):
                preds.append(p)
                refs.append(ref)
        if len(preds) > 2:
            report["model_intercomparison"]["darkskysites_grid"] = {
                **_metrics(preds, refs),
                "description": "darkskysites.com VIIRS-based model (not independent of VIIRS; not validation)",
            }

    # 4. Official observation points vs pipeline spots (descriptive)
    official = _load_official_points()
    if official is not None and spots is not None and len(spots) > 0:
        from scipy.spatial import cKDTree

        tree = cKDTree(
            np.column_stack(
                [spots.to_crs(epsg=32629).geometry.x, spots.to_crs(epsg=32629).geometry.y]
            )
        )
        o = official.to_crs(epsg=32629)
        d_km, _ = tree.query(np.column_stack([o.geometry.x, o.geometry.y]))
        d_km = d_km / 1000
        report["descriptive"]["official_points_to_nearest_spot_km"] = {
            "n": int(len(d_km)),
            "median": round(float(np.median(d_km)), 1),
            "max": round(float(d_km.max()), 1),
            "per_point": {
                pid: round(float(d), 1) for pid, d in zip(official["id"], d_km, strict=True)
            },
        }

    report["baseline"] = {
        "metric": "primary.tess_clear_sky.mae",
        "value": report["primary"].get("tess_clear_sky", {}).get("mae"),
        "model_interpretation": "clear-sky moonless zenith brightness (PSF model + 22.0 natural background)",
    }
    return report


def save_validation_report(report: dict, output_path: Path):
    """Save validation report as JSON."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False))
    logger.info("Validation report saved: %s", output_path)
