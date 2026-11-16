"""Fit CALIB_FACTOR to the TESS clear-sky pixels and estimate leave-one-out error.

The PSF model has one free scale: SQM = f(CALIB_FACTOR * PSF integral + natural).
Reports the constant in skyglow.py, the least-squares fit (squared error in mag)
and leave-one-out: fit on all pixels but one, predict that one. Only the
leave-one-out error estimates accuracy at an unseen site. skyglow.CALIB_FACTOR
is set by hand from the in-sample fit.

Usage:
    uv run python scripts/fit_calibration.py
"""

import json
from typing import Any

import numpy as np
from scipy.optimize import minimize_scalar

from stargazing_spots import skyglow
from stargazing_spots.config import REGIONS
from stargazing_spots.geo import FloatArray
from stargazing_spots.pipeline import load_composite
from stargazing_spots.skyglow import brightness_to_sqm, compute_sky_brightness
from stargazing_spots.validate import VALIDATION_DIR, group_tess_by_pixel, load_tess_sites, metrics

OUTPUT = VALIDATION_DIR / "calibration_loo.json"
K_BOUNDS = (1e-5, 10.0)
MIN_PIXELS = 3


def fit_k(integral: FloatArray, observed: FloatArray) -> float:
    """Least-squares scale factor (error in mag), searched in log space."""

    def sse(log_k: float) -> float:
        return float(np.sum((brightness_to_sqm(np.exp(log_k) * integral) - observed) ** 2))

    return float(np.exp(minimize_scalar(sse, bounds=np.log(K_BOUNDS), method="bounded").x))


def main() -> None:
    median = load_composite(REGIONS["mainland"]).median
    x, y = median.coords["x"].values, median.coords["y"].values
    sky = compute_sky_brightness(median.values)
    integral_map = sky / skyglow.CALIB_FACTOR
    sqm_map = brightness_to_sqm(sky)

    tess = load_tess_sites()
    if not tess:
        raise SystemExit("tess_clear_sky.json missing: run scripts/derive_tess_clear_sky.py")
    by_pixel, outside = group_tess_by_pixel(tess, sqm_map, x, y)
    pixels = sorted(by_pixel)
    if len(pixels) < MIN_PIXELS:
        raise SystemExit(f"only {len(pixels)} TESS pixels inside the raster")
    integral = np.array([integral_map[p] for p in pixels])
    observed = np.array([np.mean([s["clear_sky_sqm_mode"] for s in by_pixel[p]]) for p in pixels])
    current = np.array([sqm_map[p] for p in pixels])

    k_all = fit_k(integral, observed)
    loo_k = np.array(
        [fit_k(np.delete(integral, i), np.delete(observed, i)) for i in range(len(pixels))]
    )
    loo_pred = brightness_to_sqm(loo_k * integral)

    result: dict[str, Any] = {
        "method": {
            "target": "TESS clear-sky moonless zenith SQM (KDE mode), one value per model pixel",
            "model": "SQM = -2.5 log10((k * PSF_integral + 0.171) / 1000) + 12.583",
            "fit": "bounded scalar least squares on squared SQM error (mag), log k",
            "script": "scripts/fit_calibration.py",
        },
        "n_pixels": len(pixels),
        "excluded_outside_raster": outside,
        "current": {"calib_factor": skyglow.CALIB_FACTOR, **metrics(current, observed)},
        "in_sample_fit": {
            "calib_factor": round(k_all, 5),
            **metrics(brightness_to_sqm(k_all * integral), observed),
        },
        "leave_one_out": {
            "calib_factor_min": round(float(loo_k.min()), 5),
            "calib_factor_max": round(float(loo_k.max()), 5),
            **metrics(loo_pred, observed),
        },
        "sites": [
            {
                "stations": sorted({s["station"] for s in by_pixel[p]}),
                "location": by_pixel[p][0]["location"],
                "lat": by_pixel[p][0]["lat"],
                "lon": by_pixel[p][0]["lon"],
                "observed_mode": round(float(observed[i]), 3),
                "predicted_current": round(float(current[i]), 3),
                "predicted_loo": round(float(loo_pred[i]), 3),
                "k_without_site": round(float(loo_k[i]), 5),
            }
            for i, p in enumerate(pixels)
        ],
    }
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=1))
    for key in ("current", "in_sample_fit", "leave_one_out"):
        r = result[key]
        print(f"{key:14} n={r['n']} MAE={r['mae']} bias={r['bias']:+} r={r.get('pearson_r')}")


if __name__ == "__main__":
    main()
