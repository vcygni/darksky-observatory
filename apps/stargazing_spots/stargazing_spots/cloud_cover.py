"""Clear-night climatology from hourly ERA5 total cloud cover.

For each ERA5 grid cell (0.25 deg), 2006-2025:

    clear_night_fraction = dark hours with TCC < CLEAR_THRESHOLD / dark hours

An hour is dark when the Sun is below -18 deg (astronomical night) at the
cell's own latitude and longitude at that timestamp. The same definition is
used for mainland Portugal, Madeira and the Azores.
"""

import logging
import os
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import xarray as xr

logger = logging.getLogger(__name__)

CDS_DATASET = "reanalysis-era5-single-levels"

# Design choice: an hour counts as clear when total cloud cover is below 20 %.
CLEAR_THRESHOLD = 0.2
ASTRONOMICAL_NIGHT_DEG = -18.0

CLIM_START_YEAR = 2006
CLIM_END_YEAR = 2025

REGION_BOUNDS = {
    "mainland": {"lat": (36.5, 42.5), "lon": (-10.0, -6.0)},
    "madeira": {"lat": (32.0, 34.0), "lon": (-17.5, -16.0)},
    "azores": {"lat": (36.5, 40.0), "lon": (-32.0, -25.0)},
}


@dataclass
class ClearSkyConfig:
    """Configuration for the clear-night climatology."""

    clear_threshold: float = CLEAR_THRESHOLD
    start_year: int = CLIM_START_YEAR
    end_year: int = CLIM_END_YEAR
    cache_dir: Path = Path(__file__).parent.parent / "input" / "portugal" / "cache"


def sun_altitude(times: np.ndarray, lat: np.ndarray, lon: np.ndarray) -> np.ndarray:
    """Solar altitude (deg) for UTC ``times`` at ``lat``/``lon`` (deg, east positive).

    NOAA "General Solar Position Calculations" (fractional-year series for
    declination and equation of time). Inputs broadcast with numpy rules, e.g.
    times (T, 1, 1), lat (1, Y, 1), lon (1, 1, X).
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
    return np.degrees(np.arcsin(np.clip(sin_alt, -1, 1)))


def clear_dark_counts(
    tcc: np.ndarray, times: np.ndarray, lat: np.ndarray, lon: np.ndarray, threshold: float
) -> tuple[np.ndarray, np.ndarray]:
    """(dark-and-clear hours, dark hours) per cell for hourly TCC of shape (T, Y, X)."""
    alt = sun_altitude(times[:, None, None], lat[None, :, None], lon[None, None, :])
    dark = (alt < ASTRONOMICAL_NIGHT_DEG) & ~np.isnan(tcc)
    clear = dark & (tcc < threshold)
    return clear.sum(axis=0), dark.sum(axis=0)


def _get_cds_client():
    """CDS API client from $CDS_API_KEY, else ~/.cdsapirc."""
    import cdsapi

    key = os.environ.get("CDS_API_KEY")
    if key:
        return cdsapi.Client(url="https://cds.climate.copernicus.eu/api", key=key)
    return cdsapi.Client()


def _hourly_file(config: ClearSkyConfig, region: str, year: int) -> Path:
    return config.cache_dir / f"era5_tcc_hourly_{region}_{year}.nc"


def download_era5_hourly(config: ClearSkyConfig, region: str, year: int) -> Path:
    """Hourly ERA5 total cloud cover for one region and year (cached)."""
    path = _hourly_file(config, region, year)
    if path.exists():
        return path
    b = REGION_BOUNDS[region]
    path.parent.mkdir(parents=True, exist_ok=True)
    logger.info("ERA5 hourly TCC %s %d: requesting from CDS", region, year)
    _get_cds_client().retrieve(
        CDS_DATASET,
        {
            "product_type": ["reanalysis"],
            "variable": ["total_cloud_cover"],
            "year": [str(year)],
            "month": [f"{m:02d}" for m in range(1, 13)],
            "day": [f"{d:02d}" for d in range(1, 32)],
            "time": [f"{h:02d}:00" for h in range(24)],
            "area": [b["lat"][1], b["lon"][0], b["lat"][0], b["lon"][1]],
            "data_format": "netcdf",
            "download_format": "unarchived",
        },
        str(path),
    )
    return path


def compute_clear_night_fraction(
    config: ClearSkyConfig | None = None,
    region: str = "mainland",
) -> xr.DataArray:
    """Clear-night fraction on the ERA5 grid for ``region`` (see module docstring)."""
    if config is None:
        config = ClearSkyConfig()
    if region not in REGION_BOUNDS:
        raise ValueError(f"Unknown region {region!r}; expected one of {list(REGION_BOUNDS)}")

    cache_file = config.cache_dir / (
        f"era5_clear_night_hourly_{region}_{config.start_year}_{config.end_year}"
        f"_tcc{config.clear_threshold:g}.nc"
    )
    if cache_file.exists():
        logger.info("Loading cached clear-night fraction: %s", cache_file.name)
        return xr.open_dataarray(cache_file)

    clear_total = dark_total = lat = lon = None
    for year in range(config.start_year, config.end_year + 1):
        with xr.open_dataset(download_era5_hourly(config, region, year)) as ds:
            time_dim = "valid_time" if "valid_time" in ds.dims else "time"
            tcc = ds["tcc"].transpose(time_dim, "latitude", "longitude")
            lat, lon = ds["latitude"].values, ds["longitude"].values
            clear, dark = clear_dark_counts(
                tcc.values, ds[time_dim].values, lat, lon, config.clear_threshold
            )
        clear_total = clear if clear_total is None else clear_total + clear
        dark_total = dark if dark_total is None else dark_total + dark

    with np.errstate(divide="ignore", invalid="ignore"):
        fraction = np.where(dark_total > 0, clear_total / dark_total, np.nan)

    result = xr.DataArray(
        fraction,
        dims=["latitude", "longitude"],
        coords={"latitude": lat, "longitude": lon},
        attrs={
            "long_name": "Clear-night fraction",
            "units": "1",
            "definition": (
                f"dark hours (Sun < {ASTRONOMICAL_NIGHT_DEG:g} deg) with total cloud cover"
                f" < {config.clear_threshold:g}, divided by dark hours"
            ),
            "period": f"{config.start_year}-{config.end_year}",
            "source": "ERA5 hourly single levels, total_cloud_cover (Copernicus CDS)",
        },
    )
    config.cache_dir.mkdir(parents=True, exist_ok=True)
    result.to_netcdf(cache_file)
    valid = fraction[~np.isnan(fraction)]
    logger.info(
        "Clear-night fraction %s: %.1f-%.1f %% (mean %.1f %%)",
        region,
        100 * valid.min(),
        100 * valid.max(),
        100 * valid.mean(),
    )
    return result


def resample_to_viirs_grid(
    clear_fraction: xr.DataArray,
    target_x: np.ndarray,
    target_y: np.ndarray,
) -> np.ndarray:
    """Resample clear-night fraction to the VIIRS 500m grid.

    Bilinear interpolation from the ERA5 0.25 deg grid. Cells without a value
    are filled from the 3x3 neighbourhood mean, then with 0.5 if still empty.

    Args:
        clear_fraction: Source-resolution clear-night fraction (lat x lon).
        target_x: VIIRS grid longitude coordinates.
        target_y: VIIRS grid latitude coordinates.

    Returns:
        2D array matching VIIRS grid shape with interpolated clear-night fraction.
    """
    from scipy.interpolate import RegularGridInterpolator

    src_lat = clear_fraction.latitude.values
    src_lon = clear_fraction.longitude.values
    values = clear_fraction.values

    # Handle NaN for interpolation (replace with nearest valid)
    mask = np.isnan(values)
    if mask.any():
        from scipy.ndimage import uniform_filter

        filled = np.where(mask, 0, values)
        count = np.where(mask, 0, 1.0)
        filled_smooth = uniform_filter(filled, size=3, mode="constant")
        count_smooth = uniform_filter(count, size=3, mode="constant")
        with np.errstate(divide="ignore", invalid="ignore"):
            values = np.where(mask & (count_smooth > 0), filled_smooth / count_smooth, values)
        values = np.nan_to_num(values, nan=0.5)  # fallback for remaining NaN

    # Build interpolator (lat may be descending, need to flip for RegularGridInterpolator)
    if src_lat[0] > src_lat[-1]:
        src_lat = src_lat[::-1]
        values = values[::-1, :]

    interpolator = RegularGridInterpolator(
        (src_lat, src_lon),
        values,
        method="linear",
        bounds_error=False,
        fill_value=None,
    )

    # Create target grid points
    target_yy, target_xx = np.meshgrid(target_y, target_x, indexing="ij")
    points = np.column_stack([target_yy.ravel(), target_xx.ravel()])

    # Interpolate
    resampled = interpolator(points).reshape(len(target_y), len(target_x))

    return resampled
