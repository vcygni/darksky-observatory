"""PSF skyglow propagation model.

FFT convolution of VIIRS radiance with a Garstang/Duriscoe PSF kernel to
predict clear-sky zenith SQM. CALIB_FACTOR is fitted to TESS photometers.
"""

import logging
from dataclasses import dataclass

import geopandas as gpd
import numpy as np
from scipy.signal import fftconvolve

logger = logging.getLogger(__name__)

# Natural zenith luminance, 171 ucd/m^2 (Duriscoe et al. 2018, JQSRT 214).
NATURAL_SKY_MCDM2 = 0.171
# Natural sky at solar minimum, 22.0 mag/arcsec^2 (Falchi et al. 2016).
NATURAL_SKY_SQM = 22.0

# Least-squares fit to the TESS clear-sky pixels (scripts/fit_calibration.py,
# validation/portugal/calibration_loo.json).
CALIB_FACTOR = 0.07467

# Design choice: exponential attenuation with distance (per km); not fitted.
EXTINCTION_RATE = 0.0187


@dataclass
class PropagationConfig:
    """Configuration for the skyglow propagation model."""

    integration_radius_km: float = 200.0  # design choice (Falchi et al. 2016 use 195 km)
    psf_exponent: float = 2.5  # Walker's law, distance^-2.5
    # 15" grid: 0.46 km N-S, 0.36 km E-W at 39 N; treated as square
    pixel_size_km: float = 0.42
    softening_km: float = 1.0  # design choice: d0 in (d + d0)^-2.5, avoids d = 0
    extinction_rate: float = EXTINCTION_RATE


def build_psf_kernel(
    radius_km: float = 200.0,
    pixel_size_km: float = 0.42,
    exponent: float = 2.5,
    softening_km: float = 1.0,
    extinction_rate: float = EXTINCTION_RATE,
) -> np.ndarray:
    """Build 2D PSF kernel: (d + d0)^(-alpha) * exp(-beta*d).

    Self-pixel retained (physically significant at suburban sites).

    Args:
        radius_km: Integration radius.
        pixel_size_km: Pixel size in km.
        exponent: Power-law exponent.
        softening_km: Near-field offset d0.
        extinction_rate: Atmospheric extinction (per km).

    Returns:
        2D kernel array (odd dimensions, centered).
    """
    radius_px = int(radius_km / pixel_size_km)

    y = np.arange(-radius_px, radius_px + 1) * pixel_size_km
    x = np.arange(-radius_px, radius_px + 1) * pixel_size_km
    xx, yy = np.meshgrid(x, y)
    d = np.sqrt(xx**2 + yy**2)

    psf = (d + softening_km) ** (-exponent) * np.exp(-extinction_rate * d)
    psf[d > radius_km] = 0.0

    return psf


def compute_sky_brightness(
    radiance: np.ndarray,
    config: PropagationConfig | None = None,
) -> np.ndarray:
    """Convolve radiance with PSF kernel to predict artificial sky brightness.

    Args:
        radiance: 2D VIIRS radiance (nW/cm2/sr). NaN = nodata.
        config: Propagation model parameters.

    Returns:
        2D array of artificial sky brightness (mcd/m2).
    """
    if config is None:
        config = PropagationConfig()

    logger.info(
        "Building PSF kernel (radius=%.0fkm, exponent=%.1f, softening=%.1fkm)...",
        config.integration_radius_km,
        config.psf_exponent,
        config.softening_km,
    )
    psf = build_psf_kernel(
        radius_km=config.integration_radius_km,
        pixel_size_km=config.pixel_size_km,
        exponent=config.psf_exponent,
        softening_km=config.softening_km,
        extinction_rate=config.extinction_rate,
    )
    logger.info("  Kernel size: %d × %d pixels", psf.shape[0], psf.shape[1])

    radiance_clean = np.where(np.isnan(radiance), 0.0, radiance)
    radiance_clean = np.maximum(radiance_clean, 0.0)

    pixel_area_km2 = config.pixel_size_km**2

    logger.info("Running FFT convolution...")
    raw_integral = fftconvolve(radiance_clean * pixel_area_km2, psf, mode="same")
    raw_integral = np.maximum(raw_integral, 0.0)

    sky_brightness = CALIB_FACTOR * raw_integral
    sky_brightness[np.isnan(radiance)] = np.nan

    valid = sky_brightness[~np.isnan(sky_brightness)]
    logger.info("  Artificial brightness range: %.4f – %.2f mcd/m²", valid.min(), valid.max())
    logger.info(
        "  Mean: %.4f mcd/m² (%.1f%% of natural)",
        valid.mean(),
        100 * valid.mean() / NATURAL_SKY_MCDM2,
    )

    return sky_brightness


def brightness_to_sqm(artificial_mcdm2: np.ndarray) -> np.ndarray:
    """Convert artificial sky brightness to predicted SQM reading.

    SQM = -2.5 log10(L / 108000), L = artificial + natural luminance in cd/m²,
    i.e. -2.5 log10(L) + 12.583. With this zero point 0.171 mcd/m² gives
    22.0 mag/arcsec² (Falchi et al. 2016: 22 mag/arcsec² "equivalent to
    1.7 × 10−4 cd/m2").

    Args:
        artificial_mcdm2: Predicted artificial sky brightness in mcd/m².

    Returns:
        Array of predicted SQM values (mag/arcsec²). Higher = darker.
    """
    total_mcdm2 = artificial_mcdm2 + NATURAL_SKY_MCDM2
    total_cdm2 = total_mcdm2 / 1000.0  # mcd → cd

    with np.errstate(divide="ignore", invalid="ignore"):
        sqm = -2.5 * np.log10(total_cdm2) + 12.583

    return sqm


def sqm_to_bortle(sqm: np.ndarray) -> np.ndarray:
    """Classify SQM readings into Bortle scale classes.

    Approximate SQM ranges per class; the Bortle scale itself is defined by
    naked-eye observations, not SQM values.

    Args:
        sqm: Array of SQM values (mag/arcsec²).

    Returns:
        Array of Bortle class integers (1-9).
    """
    bortle = np.full_like(sqm, 9, dtype=np.int8)
    bortle[sqm >= 18.4] = 7
    bortle[sqm >= 18.9] = 6
    bortle[sqm >= 19.5] = 5
    bortle[sqm >= 20.4] = 4
    bortle[sqm >= 21.0] = 3
    bortle[sqm >= 21.5] = 2
    bortle[sqm >= 21.7] = 1
    bortle[np.isnan(sqm)] = 0
    return bortle


def classify_stargazing_quality(sqm: float) -> str:
    """Human-readable stargazing quality from SQM value.

    Labels use the same SQM cut-offs as sqm_to_bortle: excellent >= 21.5,
    good >= 21.0, acceptable >= 20.4, poor >= 19.5, else urban.
    """
    if np.isnan(sqm):
        return "unknown"
    if sqm >= 21.5:
        return "excellent"
    elif sqm >= 21.0:
        return "good"
    elif sqm >= 20.4:
        return "acceptable"
    elif sqm >= 19.5:
        return "poor"
    else:
        return "urban"


def assess_spots(
    spots: gpd.GeoDataFrame,
    radiance: np.ndarray,
    x_coords: np.ndarray,
    y_coords: np.ndarray,
    config: PropagationConfig | None = None,
) -> gpd.GeoDataFrame:
    """Run full skyglow propagation assessment on a set of spots.

    Computes the PSF-convolved sky brightness map, then samples it at
    each spot location to predict the SQM reading and Bortle class.

    Args:
        spots: GeoDataFrame with Point geometry.
        radiance: Full 2D radiance grid (median, ALL pixels including bright).
        x_coords: 1D array of x (longitude) coordinates.
        y_coords: 1D array of y (latitude) coordinates.
        config: Propagation model configuration.

    Returns:
        GeoDataFrame with added columns:
            - predicted_brightness_mcd (artificial sky brightness)
            - predicted_sqm (mag/arcsec²)
            - predicted_bortle (1-9)
            - stargazing_suitability (excellent/good/acceptable/poor/urban)
    """
    if config is None:
        config = PropagationConfig()

    spots = spots.copy()

    # Step 1: Compute full sky brightness map via PSF convolution
    sky_brightness = compute_sky_brightness(radiance, config)

    # Step 2: Convert to SQM
    sqm_map = brightness_to_sqm(sky_brightness)

    # Step 3: Sample at spot locations
    spot_cols = np.array([int(np.argmin(np.abs(x_coords - geom.x))) for geom in spots.geometry])
    spot_rows = np.array([int(np.argmin(np.abs(y_coords - geom.y))) for geom in spots.geometry])

    brightness_values = np.array(
        [
            sky_brightness[r, c]
            if 0 <= r < sky_brightness.shape[0] and 0 <= c < sky_brightness.shape[1]
            else np.nan
            for r, c in zip(spot_rows, spot_cols)
        ]
    )

    sqm_values = np.array(
        [
            sqm_map[r, c] if 0 <= r < sqm_map.shape[0] and 0 <= c < sqm_map.shape[1] else np.nan
            for r, c in zip(spot_rows, spot_cols)
        ]
    )

    # Step 4: Classify
    bortle_values = np.array([int(sqm_to_bortle(np.array([s]))[0]) for s in sqm_values])
    quality_values = [classify_stargazing_quality(s) for s in sqm_values]

    # Store results
    spots["predicted_brightness_mcd"] = np.round(brightness_values, 2)
    spots["predicted_sqm"] = np.round(sqm_values, 2)
    spots["predicted_bortle"] = bortle_values
    spots["stargazing_suitability"] = quality_values

    # Log summary
    for quality in ["excellent", "good", "acceptable", "poor", "urban"]:
        count = quality_values.count(quality)
        if count > 0:
            logger.info("  %s: %d spots", quality, count)

    return spots
