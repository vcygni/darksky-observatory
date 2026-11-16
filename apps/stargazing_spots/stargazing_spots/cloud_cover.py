"""Clear-night climatology from hourly ERA5 total cloud cover.

Per ERA5 cell (0.25 deg), 2006-2025:
    clear_night_fraction = dark hours with TCC < CLEAR_THRESHOLD / dark hours
An hour is dark when the Sun is below -18 deg at the cell's latitude and longitude.
ERA5 is read from the Destination Earth Earth Data Hub (Zarr, CC BY 4.0); needs $EDH_TOKEN.
"""

import logging
import os
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt
import xarray as xr
from scipy.interpolate import RegularGridInterpolator
from scipy.ndimage import uniform_filter

from stargazing_spots.config import CACHE_DIR, REGIONS, RegionName
from stargazing_spots.geo import FloatArray

logger = logging.getLogger(__name__)

EDH_URL = (
    "https://edh:{token}@api.earthdatahub.destine.eu/era5/era5-single-levels-atmosphere-v0.zarr"
)
CLEAR_THRESHOLD = 0.2  # design choice: an hour is clear below 20 % cloud cover
ASTRONOMICAL_NIGHT_DEG = -18.0
TIME_CHUNK = 2000  # hours per batch (bounds memory)
EMPTY_CELL_FILL = 0.5  # cells with no data and no neighbours


@dataclass(frozen=True, slots=True)
class ClearSkyConfig:
    clear_threshold: float = CLEAR_THRESHOLD
    start_year: int = 2006
    end_year: int = 2025


def sun_altitude(times: npt.ArrayLike, lat: npt.ArrayLike, lon: npt.ArrayLike) -> FloatArray:
    """Solar altitude (deg) for UTC times at lat/lon (deg, east positive); broadcasts.

    NOAA "General Solar Position Calculations" (fractional-year series).
    """
    t = np.asarray(times, dtype="datetime64[s]")
    year_start = t.astype("datetime64[Y]")
    days_in_year = (
        (year_start + np.timedelta64(1, "Y")).astype("datetime64[D]")
        - year_start.astype("datetime64[D]")
    ).astype(float)
    day_of_year = (t.astype("datetime64[D]") - year_start.astype("datetime64[D]")).astype(float) + 1
    minutes = (t - t.astype("datetime64[D]")).astype(float) / 60.0
    gamma = 2 * np.pi / days_in_year * (day_of_year - 1 + (minutes / 60 - 12) / 24)

    decl = (
        0.006918
        - 0.399912 * np.cos(gamma)
        + 0.070257 * np.sin(gamma)
        - 0.006758 * np.cos(2 * gamma)
        + 0.000907 * np.sin(2 * gamma)
        - 0.002697 * np.cos(3 * gamma)
        + 0.00148 * np.sin(3 * gamma)
    )
    eqtime = 229.18 * (
        0.000075
        + 0.001868 * np.cos(gamma)
        - 0.032077 * np.sin(gamma)
        - 0.014615 * np.cos(2 * gamma)
        - 0.040849 * np.sin(2 * gamma)
    )
    true_solar_minutes = minutes + eqtime + 4 * np.asarray(lon, dtype=float)
    hour_angle = np.radians(true_solar_minutes / 4 - 180)
    lat_rad = np.radians(np.asarray(lat, dtype=float))
    sin_alt = np.sin(lat_rad) * np.sin(decl) + np.cos(lat_rad) * np.cos(decl) * np.cos(hour_angle)
    altitude: FloatArray = np.degrees(np.arcsin(np.clip(sin_alt, -1, 1)))
    return altitude


def clear_dark_counts(
    tcc: FloatArray, times: npt.ArrayLike, lat: FloatArray, lon: FloatArray, threshold: float
) -> tuple[npt.NDArray[np.int_], npt.NDArray[np.int_]]:
    """(dark and clear hours, dark hours) per cell for hourly TCC shaped (T, Y, X)."""
    alt = sun_altitude(np.asarray(times)[:, None, None], lat[None, :, None], lon[None, None, :])
    dark = (alt < ASTRONOMICAL_NIGHT_DEG) & ~np.isnan(tcc)
    clear = dark & (tcc < threshold)
    return clear.sum(axis=0), dark.sum(axis=0)


def open_era5_tcc() -> xr.DataArray:
    """Lazy ERA5 hourly total cloud cover (longitude 0-360)."""
    token = os.environ.get("EDH_TOKEN")
    if not token:
        msg = "EDH_TOKEN is not set (Earth Data Hub API key)"
        raise RuntimeError(msg)
    tcc: xr.DataArray = xr.open_dataset(EDH_URL.format(token=token), engine="zarr", chunks={})[
        "tcc"
    ]
    return tcc


def compute_clear_night_fraction(
    region: RegionName, config: ClearSkyConfig = ClearSkyConfig()
) -> xr.DataArray:
    """Clear-night fraction on the ERA5 grid; cached in input/portugal/cache."""
    cache_file = CACHE_DIR / (
        f"era5_clear_night_hourly_{region}_{config.start_year}_{config.end_year}"
        f"_tcc{config.clear_threshold:g}.nc"
    )
    if cache_file.exists():
        return xr.open_dataarray(cache_file)

    west, south, east, north = REGIONS[region].cloud_bbox
    tcc = (
        open_era5_tcc()
        .sel(latitude=slice(north, south), longitude=slice(west % 360, east % 360))
        .transpose("valid_time", "latitude", "longitude")
    )
    lat = tcc["latitude"].values
    lon = (tcc["longitude"].values + 180) % 360 - 180
    clear_total = np.zeros((len(lat), len(lon)), dtype=np.int64)
    dark_total = np.zeros_like(clear_total)
    for year in range(config.start_year, config.end_year + 1):
        yearly = tcc.sel(valid_time=slice(f"{year}-01-01", f"{year}-12-31T23"))
        times = yearly["valid_time"].values
        for start in range(0, len(times), TIME_CHUNK):
            part = slice(start, start + TIME_CHUNK)
            clear, dark = clear_dark_counts(
                yearly[part].values, times[part], lat, lon, config.clear_threshold
            )
            clear_total += clear
            dark_total += dark
        logger.info("ERA5 cloud cover %s %d: %d hours", region, year, len(times))

    with np.errstate(divide="ignore", invalid="ignore"):
        fraction = np.where(dark_total > 0, clear_total / dark_total, np.nan)
    result = xr.DataArray(
        fraction,
        dims=["latitude", "longitude"],
        coords={"latitude": lat, "longitude": lon},
        attrs={
            "long_name": "clear-night fraction",
            "units": "1",
            "definition": (
                f"dark hours (Sun < {ASTRONOMICAL_NIGHT_DEG:g} deg) with total cloud cover"
                f" < {config.clear_threshold:g}, divided by dark hours"
            ),
            "period": f"{config.start_year}-{config.end_year}",
            "source": "ERA5 hourly single levels, tcc (Earth Data Hub, CC BY 4.0)",
        },
    )
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    result.to_netcdf(cache_file)
    return result


def resample_to_viirs_grid(
    clear_fraction: xr.DataArray, target_x: FloatArray, target_y: FloatArray
) -> FloatArray:
    """Bilinear interpolation to the VIIRS grid.

    Empty ERA5 cells take the mean of their 3x3 neighbourhood, else EMPTY_CELL_FILL.
    """
    src_lat = clear_fraction.latitude.values
    src_lon = clear_fraction.longitude.values
    values = clear_fraction.values

    mask = np.isnan(values)
    if mask.any():
        filled = uniform_filter(np.where(mask, 0, values), size=3, mode="constant")
        count = uniform_filter(np.where(mask, 0, 1.0), size=3, mode="constant")
        with np.errstate(divide="ignore", invalid="ignore"):
            values = np.where(mask & (count > 0), filled / count, values)
        values = np.nan_to_num(values, nan=EMPTY_CELL_FILL)

    if src_lat[0] > src_lat[-1]:
        src_lat, values = src_lat[::-1], values[::-1, :]
    interpolator = RegularGridInterpolator(
        (src_lat, src_lon), values, method="linear", bounds_error=False, fill_value=None
    )
    yy, xx = np.meshgrid(target_y, target_x, indexing="ij")
    resampled: FloatArray = interpolator(np.column_stack([yy.ravel(), xx.ravel()])).reshape(
        len(target_y), len(target_x)
    )
    return resampled
