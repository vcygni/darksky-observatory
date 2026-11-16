"""Artificial sky brightness from VIIRS radiance with a power-law point spread function.

B = CALIB_FACTOR * (radiance * pixel_area) convolved with PSF(d) = (d + d0)^-2.5 * exp(-beta d),
converted to zenith SQM with the natural background added.
"""

from dataclasses import dataclass

import geopandas as gpd
import numpy as np
import numpy.typing as npt
from scipy.signal import fftconvolve

from stargazing_spots.geo import FloatArray, sample

# Natural zenith luminance, 171 ucd/m^2 (Duriscoe et al. 2018, JQSRT 214).
NATURAL_SKY_MCDM2 = 0.171
# Least-squares fit to the TESS clear-sky pixels (scripts/fit_calibration.py,
# validation/portugal/calibration_loo.json).
CALIB_FACTOR = 0.07467
# Design choice: exponential attenuation with distance (per km); not fitted.
EXTINCTION_RATE = 0.0187
# SQM zero point: L [cd/m^2] = 108000 * 10^(-0.4 SQM); 0.171 mcd/m^2 -> 22.0 mag/arcsec^2.
_SQM_ZERO_POINT = 12.583

# Approximate SQM lower bounds per Bortle class; the scale itself is defined by
# naked-eye observations, not SQM values.
_BORTLE_BOUNDS = ((21.7, 1), (21.5, 2), (21.0, 3), (20.4, 4), (19.5, 5), (18.9, 6), (18.4, 7))


@dataclass(frozen=True, slots=True)
class PropagationConfig:
    integration_radius_km: float = 200.0  # design choice (Falchi et al. 2016 use 195 km)
    psf_exponent: float = 2.5  # Walker's law, distance^-2.5
    # 15" grid: 0.46 km N-S, 0.36 km E-W at 39 N; treated as square
    pixel_size_km: float = 0.42
    softening_km: float = 1.0  # design choice: d0 in (d + d0)^-2.5, avoids d = 0
    extinction_rate: float = EXTINCTION_RATE


def build_psf_kernel(config: PropagationConfig = PropagationConfig()) -> FloatArray:
    """Square kernel (odd size, centred), zero beyond the integration radius."""
    radius_px = int(config.integration_radius_km / config.pixel_size_km)
    axis = np.arange(-radius_px, radius_px + 1) * config.pixel_size_km
    xx, yy = np.meshgrid(axis, axis)
    d = np.sqrt(xx**2 + yy**2)
    psf: FloatArray = (d + config.softening_km) ** (-config.psf_exponent) * np.exp(
        -config.extinction_rate * d
    )
    psf[d > config.integration_radius_km] = 0.0
    return psf


def compute_sky_brightness(
    radiance: FloatArray, config: PropagationConfig = PropagationConfig()
) -> FloatArray:
    """Artificial zenith brightness (mcd/m^2); NaN where the radiance is NaN."""
    source = np.maximum(np.where(np.isnan(radiance), 0.0, radiance), 0.0)
    integral = fftconvolve(source * config.pixel_size_km**2, build_psf_kernel(config), mode="same")
    brightness: FloatArray = CALIB_FACTOR * np.maximum(integral, 0.0)
    brightness[np.isnan(radiance)] = np.nan
    return brightness


def brightness_to_sqm(artificial_mcdm2: npt.ArrayLike) -> FloatArray:
    """SQM (mag/arcsec^2) of artificial plus natural luminance."""
    total_cdm2 = (np.asarray(artificial_mcdm2) + NATURAL_SKY_MCDM2) / 1000.0
    with np.errstate(divide="ignore", invalid="ignore"):
        sqm: FloatArray = -2.5 * np.log10(total_cdm2) + _SQM_ZERO_POINT
    return sqm


def sqm_to_bortle(sqm: npt.ArrayLike) -> npt.NDArray[np.int8]:
    """Approximate Bortle class (1-9); 0 for NaN."""
    values = np.asarray(sqm, dtype=np.float64)
    bortle = np.full(values.shape, 9, dtype=np.int8)
    for bound, cls in reversed(_BORTLE_BOUNDS):
        bortle[values >= bound] = cls
    bortle[np.isnan(values)] = 0
    return bortle


def assess_spots(
    spots: gpd.GeoDataFrame, radiance: FloatArray, x: FloatArray, y: FloatArray
) -> gpd.GeoDataFrame:
    """Add predicted artificial brightness, SQM and Bortle class at each spot's pixel."""
    brightness = compute_sky_brightness(radiance)
    lon, lat = spots.geometry.x.values, spots.geometry.y.values
    spot_brightness = sample(brightness, x, y, lon, lat)
    spot_sqm = sample(brightness_to_sqm(brightness), x, y, lon, lat)
    return spots.assign(
        predicted_brightness_mcd=np.round(spot_brightness, 2),
        predicted_sqm=np.round(spot_sqm, 2),
        predicted_bortle=sqm_to_bortle(spot_sqm),
    )
