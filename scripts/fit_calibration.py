"""Fit CALIB_FACTOR against TESS clear-sky values, with leave-one-out error.

The PSF model has one free scale: SQM = f(CALIB_FACTOR * PSF-integral + natural).
CALIB_FACTOR = 0.04237 in skyglow.py has no fitting code in the repository and
was checked against the same points it was reportedly fitted on. This script:

  1. builds the PSF integral once (CALIB_FACTOR divided out);
  2. takes TESS clear-sky sites, one value per model pixel (same grouping as
     validate.run_validation);
  3. reports metrics for the current constant, an in-sample least-squares fit
     (squared error in mag), and leave-one-out: for each pixel, fit on all the
     others and predict the held-out one. Only the LOO error estimates accuracy
     at a site the calibration has not seen.

It does not change skyglow.py.

Usage:
    cd apps/stargazing_spots
    uv run python ../../scripts/fit_calibration.py
"""

import json
from pathlib import Path

import joblib
import numpy as np
from scipy.optimize import minimize_scalar

from stargazing_spots import skyglow
from stargazing_spots.skyglow import (
    PropagationConfig,
    brightness_to_sqm,
    compute_sky_brightness,
)
from stargazing_spots.validate import (
    VALIDATION_DIR,
    _load_tess_sites,
    _metrics,
    group_tess_by_pixel,
)

APP = Path(__file__).resolve().parent.parent / "apps" / "stargazing_spots"
OUTPUT = VALIDATION_DIR / "calibration_loo.json"
K_BOUNDS = (1e-5, 10.0)


def fit_k(integral: np.ndarray, observed: np.ndarray) -> float:
    """Least-squares CALIB_FACTOR (error in mag), searched in log space."""

    def sse(log_k: float) -> float:
        return float(
            np.sum((brightness_to_sqm(np.exp(log_k) * integral) - observed) ** 2)
        )

    res = minimize_scalar(sse, bounds=np.log(K_BOUNDS), method="bounded")
    return float(np.exp(res.x))


def main() -> None:
    years = [
        joblib.load(APP / f"input/portugal/cache/VNP46A4_{y}.joblib")
        for y in ("2023", "2024", "2025")
    ]
    radiance = np.nanmedian(
        np.stack([d["NearNadir_Composite_Snow_Free"].values[0] for d in years]), axis=0
    )
    x = years[0].coords["x"].values
    y = years[0].coords["y"].values
    sky = compute_sky_brightness(
        np.where(radiance < 0, np.nan, radiance), PropagationConfig()
    )
    integral_map = sky / skyglow.CALIB_FACTOR  # PSF integral, model scale removed
    sqm_map = brightness_to_sqm(sky)

    tess = _load_tess_sites()
    if not tess:
        raise SystemExit(
            "tess_clear_sky.json missing: run scripts/derive_tess_clear_sky.py"
        )
    by_pixel, outside = group_tess_by_pixel(tess, sqm_map, x, y)
    pixels = sorted(by_pixel)
    integral = np.array([integral_map[p] for p in pixels])
    observed = np.array(
        [np.mean([s["clear_sky_sqm_mode"] for s in by_pixel[p]]) for p in pixels]
    )
    n = len(pixels)
    if n < 3:
        raise SystemExit(f"only {n} TESS pixels inside the raster; too few to fit")

    k_all = fit_k(integral, observed)
    loo_k = np.array(
        [fit_k(np.delete(integral, i), np.delete(observed, i)) for i in range(n)]
    )
    loo_pred = brightness_to_sqm(loo_k * integral)

    sites = []
    for i, p in enumerate(pixels):
        s0 = by_pixel[p][0]
        sites.append(
            {
                "stations": sorted({s["station"] for s in by_pixel[p]}),
                "location": s0["location"],
                "lat": s0["lat"],
                "lon": s0["lon"],
                "observed_mode": round(float(observed[i]), 3),
                "predicted_current": round(float(sqm_map[p]), 3),
                "predicted_loo": round(float(loo_pred[i]), 3),
                "k_without_site": round(float(loo_k[i]), 5),
            }
        )

    result = {
        "method": {
            "target": "TESS clear-sky moonless zenith SQM (KDE mode), one value per model pixel",
            "model": "SQM = -2.5 log10((k * PSF_integral + 0.171) / 1000) + 12.583",
            "fit": "bounded scalar least squares on squared SQM error (mag), log k",
            "script": "scripts/fit_calibration.py",
        },
        "n_pixels": n,
        "excluded_outside_raster": outside,
        "current": {
            "calib_factor": skyglow.CALIB_FACTOR,
            **_metrics(sqm_map_at(sqm_map, pixels), observed),
        },
        "in_sample_fit": {
            "calib_factor": round(k_all, 5),
            **_metrics(brightness_to_sqm(k_all * integral), observed),
        },
        "leave_one_out": {
            "calib_factor_min": round(float(loo_k.min()), 5),
            "calib_factor_max": round(float(loo_k.max()), 5),
            **_metrics(loo_pred, observed),
        },
        "sites": sites,
    }
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=1))
    for key in ("current", "in_sample_fit", "leave_one_out"):
        r = result[key]
        k = r.get(
            "calib_factor", f"{r.get('calib_factor_min')}-{r.get('calib_factor_max')}"
        )
        print(
            f"{key:14} k={k}  n={r['n']}  MAE={r['mae']}  bias={r['bias']:+}  "
            f"RMSE={r['rmse']}  r={r.get('pearson_r')}"
        )
    print(f"wrote {OUTPUT}")


def sqm_map_at(sqm_map: np.ndarray, pixels: list[tuple[int, int]]) -> np.ndarray:
    return np.array([sqm_map[p] for p in pixels])


if __name__ == "__main__":
    main()
