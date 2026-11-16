"""Per-region run and the merged Portugal output."""

import json
import logging
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import geopandas as gpd
import joblib
import pandas as pd
import xarray as xr

from stargazing_spots import __version__
from stargazing_spots.access_points import enrich_geojson_file
from stargazing_spots.assess import assess, select_spots
from stargazing_spots.change_detection import write_change_detection
from stargazing_spots.config import REGIONS, VIIRS_VARIABLE, YEARS, Region, viirs_cache
from stargazing_spots.enrichment import score_spots
from stargazing_spots.enrichment_raster import features_on_dark_pixels
from stargazing_spots.export import to_cog, to_geojson, to_parquet
from stargazing_spots.osm_extract import extract_features_from_pbf
from stargazing_spots.processing import (
    DEFAULT_THRESHOLD,
    TemporalComposite,
    classify_temporal,
    clean_radiance,
)
from stargazing_spots.sensitivity import run_sensitivity
from stargazing_spots.stac_catalog import create_darksky_catalog
from stargazing_spots.uncertainty import compute_confidence_layer, enrich_spots_with_confidence

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class RunOptions:
    output_dir: Path
    threshold: float
    osm_pbf: Path
    access_points: bool = True
    sensitivity: bool = False


def load_radiance(path: Path) -> xr.DataArray:
    """Annual VIIRS composite from a joblib cache, negatives set to NaN."""
    dataset = joblib.load(path)
    return clean_radiance(dataset[VIIRS_VARIABLE].squeeze("time", drop=True))


def load_layers(region: Region) -> list[xr.DataArray]:
    return [load_radiance(viirs_cache(region, year)) for year in YEARS]


def load_composite(region: Region, threshold: float = DEFAULT_THRESHOLD) -> TemporalComposite:
    return classify_temporal(load_layers(region), threshold)


def run_region(region: Region, features: gpd.GeoDataFrame, options: RunOptions) -> gpd.GeoDataFrame:
    """Classify, assess and select one region's spots; write its rasters and vectors."""
    out = options.output_dir / region.name
    out.mkdir(parents=True, exist_ok=True)
    layers = load_layers(region)
    composite = classify_temporal(layers, options.threshold)
    confidence = compute_confidence_layer(composite, options.threshold)

    darksky_cog = out / "portugal_darksky.tif"
    to_cog(composite.dark_sky, darksky_cog)
    to_cog(composite.stability, out / "temporal_stability.tif")
    to_cog(composite.trend, out / "temporal_trend.tif")
    to_cog(confidence, out / "dark_confidence.tif")
    write_change_detection(layers, YEARS, out / "change_detection")
    if options.sensitivity:
        run_sensitivity(composite.median).to_csv(out / "sensitivity_analysis.csv", index=False)

    candidates = features_on_dark_pixels(composite, features, options.threshold)
    candidates = score_spots(candidates[candidates["name"].notna()])
    candidates = enrich_spots_with_confidence(candidates, confidence)
    x = composite.median.coords["x"].to_numpy()
    y = composite.median.coords["y"].to_numpy()
    spots = select_spots(assess(candidates, composite.median.values, x, y, region.name))

    spots_geojson = out / "spots.geojson"
    to_geojson(
        spots,
        spots_geojson,
        {"threshold_nw_cm2_sr": options.threshold, "spots_count": len(spots), "crs": "EPSG:4326"},
    )
    to_parquet(spots, out / "spots.parquet")
    create_darksky_catalog(
        out / "stac",
        region.name,
        region.viirs_bbox,
        spots_geojson,
        darksky_cog,
        len(spots),
        options.threshold,
    )
    logger.info("%s: %d spots", region.name, len(spots))
    return gpd.read_file(spots_geojson).assign(region=region.name)


def run_all(options: RunOptions) -> None:
    """All regions, merged spots and drivable access points."""
    started = time.perf_counter()
    options.output_dir.mkdir(parents=True, exist_ok=True)
    features, _ = extract_features_from_pbf(options.osm_pbf)
    per_region = {name: run_region(r, features, options) for name, r in REGIONS.items()}
    counts = {name: {"spots_count": len(s)} for name, s in per_region.items()}

    merged = gpd.GeoDataFrame(pd.concat(per_region.values(), ignore_index=True))
    merged_path = options.output_dir / "spots_all.geojson"
    to_geojson(
        merged,
        merged_path,
        {
            "threshold_nw_cm2_sr": options.threshold,
            "regions": list(REGIONS),
            "temporal_years": list(YEARS),
            "total_spots": len(merged),
            "per_region": counts,
        },
    )
    to_parquet(merged, options.output_dir / "spots_all.parquet")
    if options.access_points:
        enrich_geojson_file(merged_path, options.osm_pbf)

    metadata: dict[str, Any] = {
        "run_timestamp": datetime.now(UTC).isoformat(),
        "pipeline_version": __version__,
        "parameters": {
            "threshold_nw": options.threshold,
            "temporal_years": list(YEARS),
            "regions": list(REGIONS),
        },
        "metrics": {"total_spots": len(merged), "per_region": counts},
        "total_time_s": round(time.perf_counter() - started, 2),
    }
    (options.output_dir / "run_metadata.json").write_text(json.dumps(metadata, indent=2))
    logger.info("Total: %d spots in %.0f s", len(merged), metadata["total_time_s"])
