"""Clear-sky, moonless zenith brightness per TESS photometer from the raw readings.

Replaces tess_station_summary.json (all-time max / p95 of every reading, a
single position per station) with an estimate that matches what the model
predicts: the zenith sky brightness of a clear, moonless, astronomical night.

Per monthly .dat file (IDA/NSBM community standard format):
  * the file's own header position is used (7 stations moved; stars218 by 121 km);
  * files the supplier marks "This photometer may not have been calibrated"
    (zero point 20.50 default) are excluded: their absolute scale is unknown;
  * readings with MSAS <= 0 (saturated / daylight) are dropped.
Per reading (Skyfield + JPL DE421, geometric altitude, header position):
  * astronomical night: Sun altitude < -18 deg (IAU/USNO definition);
  * moonless: Moon altitude < 0 deg (centre below the horizon).
Per site (station + header position): the clear-sky value is the mode of the
remaining readings, from a Gaussian KDE with Scott's-rule bandwidth evaluated
on a 0.005 mag grid (binned KDE). Clear nights dominate the moonless dark-time
distribution, so its mode estimates clear-sky brightness without a cloud
threshold. The median is reported alongside as a sensitivity check.

Usage:
    uv run python scripts/derive_tess_clear_sky.py
"""

import json
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt
import pandas as pd
from skyfield.api import Loader, wgs84
from skyfield.timelib import Timescale
from skyfield.vectorlib import VectorSum

ROOT = Path(__file__).parent.parent
TESS_DIR = ROOT / "validation" / "portugal" / "tess-ida"
EPHEMERIS_DIR = ROOT / "apps" / "stargazing_spots" / "input" / "portugal" / "cache" / "ephemeris"
OUTPUT = TESS_DIR / "tess_clear_sky.json"

SUN_MAX_ALT = -18.0
MOON_MAX_ALT = 0.0
KDE_GRID_STEP = 0.005
MIN_READINGS = 2  # a KDE needs at least two values
ALT_CHUNK = 50_000  # readings per Skyfield call (bounds memory)


@dataclass(slots=True)
class Site:
    frames: list[pd.DataFrame] = field(default_factory=list)
    files: int = 0
    zero_points: set[float] = field(default_factory=set)
    location: str = ""


def read_header(path: Path) -> dict[str, Any]:
    header: dict[str, Any] = {"calibrated": True}
    with path.open(encoding="utf-8", errors="replace") as f:
        for line in f:
            if not line.startswith("#"):
                break
            if line.startswith("# Position:"):
                parts = [x.strip() for x in line.split(":", 1)[1].split(",")]
                lat, lon, *ele = [float(x) if x not in ("", "None") else None for x in parts[:3]]
                header.update(lat=lat, lon=lon, ele=ele[0] if ele else None)
            elif line.startswith("# Location name:"):
                header["location"] = line.split(":", 1)[1].strip()
            elif line.startswith("# TESS zero point:"):
                header["zp"] = float(line.split(":", 1)[1])
            elif "may not have been calibrated" in line:
                header["calibrated"] = False
    return header


def read_readings(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, sep=";", comment="#", header=None, usecols=[0, 5], names=["utc", "msas"])
    df["utc"] = pd.to_datetime(df["utc"], utc=True, errors="coerce")
    df["msas"] = pd.to_numeric(df["msas"], errors="coerce")
    return df.dropna()


def kde_mode(values: np.ndarray) -> float:
    """Mode of a Gaussian KDE (Scott's rule) via a binned approximation."""
    bw = 1.06 * values.std(ddof=1) * len(values) ** (-1 / 5)  # Scott's rule, Gaussian kernel
    lo, hi = values.min() - 3 * bw, values.max() + 3 * bw
    edges = np.arange(lo, hi + KDE_GRID_STEP, KDE_GRID_STEP)
    counts, _ = np.histogram(values, bins=edges)
    half = int(np.ceil(4 * bw / KDE_GRID_STEP))
    kernel = np.exp(-0.5 * (np.arange(-half, half + 1) * KDE_GRID_STEP / bw) ** 2)
    density = np.convolve(counts, kernel, mode="same")
    centres = (edges[:-1] + edges[1:]) / 2
    return float(centres[np.argmax(density)])


def dark_moonless_mask(
    ts: Timescale, observer: VectorSum, sun: VectorSum, moon: VectorSum, utc: pd.Series
) -> npt.NDArray[np.bool_]:
    """Sun < SUN_MAX_ALT and Moon < MOON_MAX_ALT, evaluated in chunks.

    Skyfield allocates several (3, N) float64 arrays per observe/apparent call;
    one call over a whole station reached 13 GB RSS and exhausted swap.
    Chunking gives identical results with bounded memory.
    """
    times = np.asarray(utc.dt.to_pydatetime())  # ndarray on current and future pandas
    out = np.empty(len(times), dtype=bool)
    for start in range(0, len(times), ALT_CHUNK):
        t = ts.from_datetimes(times[start : start + ALT_CHUNK])
        here = observer.at(t)
        sun_alt = here.observe(sun).apparent().altaz()[0].degrees
        moon_alt = here.observe(moon).apparent().altaz()[0].degrees
        out[start : start + ALT_CHUNK] = (sun_alt < SUN_MAX_ALT) & (moon_alt < MOON_MAX_ALT)
    return out


def main() -> None:
    load = Loader(str(EPHEMERIS_DIR))
    eph = load("de421.bsp")
    ts = load.timescale(builtin=True)
    earth, sun, moon = eph["earth"], eph["sun"], eph["moon"]

    sites: defaultdict[tuple[str, float, float, float | None], Site] = defaultdict(Site)
    excluded: defaultdict[str, int] = defaultdict(int)
    no_position: defaultdict[str, int] = defaultdict(int)
    for station_dir in sorted((TESS_DIR / "IDA").iterdir()):
        for path in sorted(station_dir.glob("*.dat")):
            h = read_header(path)
            if not h["calibrated"]:
                excluded[station_dir.name] += 1
                continue
            if h.get("lat") is None or h.get("lon") is None:
                # Stations move (stars218: 121 km); never assume a missing position.
                no_position[station_dir.name] += 1
                continue
            key = (station_dir.name, h["lat"], h["lon"], h["ele"])
            df = read_readings(path)
            df = df[df["msas"] > 0]
            if df.empty:
                continue
            site = sites[key]
            site.frames.append(df)
            site.files += 1
            site.zero_points.add(h["zp"])
            site.location = h.get("location", "")

    out: list[dict[str, Any]] = []
    for (station, lat, lon, ele), site in sorted(sites.items()):
        df = pd.concat(site.frames, ignore_index=True).drop_duplicates("utc").sort_values("utc")
        observer = earth + wgs84.latlon(lat, lon, elevation_m=ele or 0.0)  # missing ele: 0 m
        dark = dark_moonless_mask(ts, observer, sun, moon, df["utc"])
        values = df.loc[dark, "msas"].to_numpy()
        nights = (
            df.loc[dark, "utc"].dt.tz_convert("UTC").sub(pd.Timedelta(hours=12)).dt.date.nunique()
        )
        rec = {
            "station": station,
            "location": site.location,
            "lat": lat,
            "lon": lon,
            "ele_m": ele,
            "files": site.files,
            "zero_points": sorted(site.zero_points),
            "readings_total": len(df),
            "readings_dark_moonless": len(values),
            "nights_dark_moonless": int(nights),
            "first": df["utc"].min().isoformat(),
            "last": df["utc"].max().isoformat(),
        }
        if len(values) >= MIN_READINGS:
            rec["clear_sky_sqm_mode"] = round(kde_mode(values), 3)
            rec["sqm_median"] = round(float(np.median(values)), 3)
        out.append(rec)
        print(
            f"{station:9} {lat:9.5f} {lon:10.5f} dark+moonless {len(values):8d} readings "
            f"{nights:4d} nights  mode {rec.get('clear_sky_sqm_mode', float('nan')):6.2f}  "
            f"median {rec.get('sqm_median', float('nan')):6.2f}  {site.location[:40]}"
        )

    result = {
        "method": {
            "sun_max_alt_deg": SUN_MAX_ALT,
            "moon_max_alt_deg": MOON_MAX_ALT,
            "ephemeris": "JPL DE421 via Skyfield",
            "estimator": "mode of Gaussian KDE (Scott's rule), binned at 0.005 mag",
            "excluded": (
                "files flagged 'may not have been calibrated' by the supplier;"
                " files with no header position; MSAS <= 0"
            ),
            "script": "scripts/derive_tess_clear_sky.py",
        },
        "excluded_uncalibrated_files": dict(excluded),
        "excluded_files_without_position": dict(no_position),
        "sites": out,
    }
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=1))
    print(f"\nwrote {OUTPUT.relative_to(ROOT)}: {len(out)} sites")
    print(f"uncalibrated files excluded: {dict(excluded)}")


if __name__ == "__main__":
    main()
