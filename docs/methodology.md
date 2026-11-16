# Methodology

**Pipeline version:** 0.7.0
**Output:** 597 spots (mainland 469, Madeira 56, Azores 72)

Parameters marked *design choice* are set by hand and not fitted to observations.

---

## 1. Data Acquisition

### VIIRS VNP46A4

| Parameter | Value |
|-----------|-------|
| Product | VNP46A4v001 (Black Marble annual) |
| Variable | `NearNadir_Composite_Snow_Free` |
| Grid | 15 arc-seconds (~460 m N-S, ~360 m E-W at 39° N) |
| Units | nW/cm^2/sr |
| Years | 2023, 2024, 2025 |
| Tiles | h14v05, h15v05, h16v05, h17v04, h17v05 |

Quality flags 1 (poor) and 255 (fill) are removed at ingestion.

### OpenStreetMap

Candidate features (`osm_extract.py`): nodes tagged with `enrichment.DEFAULT_OSM_TAGS` (peaks, hills, viewpoints, picnic sites, shelters, observatories, ...) from the Geofabrik Portugal extract (replication timestamp 2026-10-06T20:21:06Z), clipped to the Portugal land boundary (union of the 308 OSM municipalities, `scripts/build_boundary.py`): 11,080 nodes. The same extract feeds the access-point step.

---

## 2. Temporal Compositing

```
R_median = median(R_2023, R_2024, R_2025)
sigma    = std(R_2023, R_2024, R_2025)
trend    = R_2025 - R_2023   [nW/cm^2/sr]
```

---

## 3. Dark-Sky Classification

Threshold: **3.0 nW/cm^2/sr** on `R_median` (design choice; `sensitivity.py` compares other values and Otsu's split).

Per-pixel confidence (weights are a design choice):
```
C = 0.40 * C_distance + 0.30 * C_stability + 0.30 * C_consistency
```

- `C_distance`: sigmoid of (threshold - R) / threshold
- `C_stability`: 1 - min(sigma / threshold, 1)
- `C_consistency`: years below threshold / 3

---

## 4. PSF Skyglow Propagation

```
PSF(d) = (d + d_0)^(-2.5) * exp(-beta * d)
B_artificial = CALIB_FACTOR * (radiance * pixel_area) ⊛ PSF      (FFT)
SQM = -2.5 * log10((B_artificial + B_natural) / 1000 / 108000)   (B in mcd/m^2)
```

| Parameter | Value | Source |
|-----------|-------|--------|
| Exponent | 2.5 | Walker's law (Walker 1977) |
| d_0 | 1 km | design choice (avoids d = 0) |
| beta | 0.0187 km^-1 | design choice |
| Radius | 200 km | design choice (Falchi et al. 2016 use 195 km) |
| Pixel size | 0.42 km | grid treated as square |
| B_natural | 0.171 mcd/m^2 | Duriscoe et al. 2018 |
| CALIB_FACTOR | 0.07467 | least squares on 16 TESS pixels (`scripts/fit_calibration.py`) |

With the 108000 cd/m^2 zero point, 0.171 mcd/m^2 corresponds to 22.0 mag/arcsec^2 (Falchi et al. 2016: 22 mag/arcsec^2 "equivalent to 1.7 × 10−4 cd/m2"). `predicted_sqm` is the model value at the spot's pixel; no elevation correction.

---

## 5. Cloud Climatology

ERA5 hourly total cloud cover (TCC), 0.25°, 2006-2025, all regions, read from the Destination Earth Earth Data Hub. Per grid cell:
```
clear_night_fraction = (dark hours with TCC < 0.2) / (dark hours)
```
Dark: Sun altitude < -18° at the cell's latitude and longitude at each hour (NOAA solar position equations; within 0.6° of Skyfield/DE421 in the tests). The 0.2 threshold is a design choice. Bilinear interpolation to the VIIRS grid.

---

## 6. Sky View Factor

Terrain SVF from Copernicus GLO-30 (16 azimuth rays, 1.5 km radius; design choice):
```
terrain_SVF = 1 - mean(sin(max_horizon_angle_i))
effective_SVF = terrain_SVF * (1 - canopy_fraction)        (Hansen GFC)
```
Candidates with effective_SVF < 0.7 are removed (design choice).

---

## 7. Land Cover

ESA WorldCover 10 m class; tree cover (class 10) scored from Hansen canopy fraction. Scores are a design choice.

| Class | Score |
|-------|-------|
| Tree cover | 1 - canopy_fraction |
| Grassland, bare/sparse | 1.0 |
| Shrubland, moss/lichen | 0.8 |
| Cropland | 0.6 |
| Snow/ice | 0.5 |
| Herbaceous wetland | 0.4 |
| Built-up, water, mangroves | 0.0 (removed) |

---

## 8. Terrain Slope and Elevation

Horn (1981) slope from Copernicus GLO-30. Scores are a design choice:

| Slope | Score |
|-------|-------|
| < 5° | 1.0 |
| 5-15° | 0.8 |
| 15-30° | 0.4 |
| ≥ 30° | 0.0 |

Elevation (DEM) normalised linearly over 0-1500 m, capped at 1 (design choice).

---

## 9. SSI and Selection

```
SSI = 100 * SUM(w_i * s_i)
```

| Factor | Score | Weight |
|--------|-------|--------|
| Darkness | (SQM - 20) / 2, clipped to [0, 1] | 0.30 |
| Clear sky | clear_night_fraction | 0.25 |
| Sky openness | (SVF - 0.5) / 0.5, clipped | 0.15 |
| Land cover | §7 | 0.15 |
| Slope | §8 | 0.10 |
| Elevation | §8 | 0.05 |

Weights and ranges are a design choice. `ssi_class` labels: excellent ≥ 80, good ≥ 65, acceptable ≥ 50, marginal ≥ 35.

**Selection.** Within each region, the physically suitable candidates are split into two SSI classes with maximum between-class variance (Otsu 1979; a two-class Jenks natural-breaks split) and the upper class is kept. Splits in the current run: mainland 58.8, Madeira 47.4, Azores 56.6. The SSI distributions are unimodal, so the split falls near the median; keeping the upper class is a design choice. Each spot carries `ssi_percentile`, its rank within the region.

The official observation points could not set this cut-off: they are public outreach sites, and the lowest scores SSI 18.8, so a cut that keeps all of them keeps every candidate.

---

## 10. Spatial Filtering

- **Deduplication:** spots visited best-first; any spot within 1 km of a kept spot is dropped (design choice)
- **Density cap:** at most 5 spots per 0.25° cell, grid anchored at fixed multiples of 0.25° (design choice)

---

## 11. Tiering and Access

**Destination tier:** viewpoints, campsites, picnic sites, wilderness huts, shelters, observatories, nature reserves, bird hides. **Candidate tier:** everything else.

Tag-based access hints (`access_check.py`): drive_up / short_walk / hike_required / boat_required from the OSM feature type, with private/gated features excluded. Heuristics; the scores are a design choice.

### Drivable access points (`access_points.py`)

Each spot gets the nearest point on a road a car can legally use **and stop on**, measured on the local OSM extract:

- **Drivable road:** OSRM car profile (`profiles/car.lua` @214ba8f, 2026-09-27) reproduced in Python: speed-table highway types, access hierarchy motorcar > motor_vehicle > vehicle > access, OSRM white/blacklists, blocked ways, vehicle dimensions. No `highway=track`.
- **Legal stopping:** Código da Estrada art. 72.º n.º 2 b) and art. 75.º (as amended by Lei 72/2013) forbid stopping on motorways, their accesses and *vias reservadas a automóveis e motociclos* → `motorway`, `motorway_link`, `motorroad=yes` excluded.
- **Public access:** of OSRM's restricted values only `destination` is accepted.
- **Threshold:** `MAX_WALK_M = 358 m`, the largest road distance among the 18 official observation points (`scripts/derive_access_thresholds.py`).

Spots beyond the threshold get `access_kind = "none"`. Current output: 290 of 597 spots have a drivable access point (mainland 195/469, Madeira 43/56, Azores 52/72); walk median 64 m.

---

## 12. Change Detection

```
delta_R = R_2025 - R_2023
```

A pixel is brightening or darkening when |delta_R| >= 1.0 nW/cm^2/sr (design choice). With three years this is inter-annual variability, not a trend.

---

## 13. Export Formats

| Format | Use |
|--------|-----|
| GeoJSON | Web applications |
| GeoParquet | Analysis |
| Cloud Optimized GeoTIFF | Rasters |
| STAC Catalog | Discovery, provenance |

---

## 14. Validation Summary

`make validate` (`scripts/run_validation.py`) and `scripts/fit_calibration.py`, 2026-11-16. Details in [validation_report.md](validation_report.md).

| Role | Source | N | MAE (mag) | Bias (mag) | Pearson r |
|------|--------|---|-----------|------------|-----------|
| Primary | TESS clear-sky (mode), fitted CALIB_FACTOR | 16 pixels | 0.555 | +0.138 | 0.722 |
| Primary | TESS clear-sky, leave-one-out | 16 pixels | 0.593 | +0.130 | 0.712 |
| Indicative | Published SQM passing the audit | 2 | 0.066 | −0.055 | -- |
| Descriptive | Official observation points to nearest spot | 18 | median 5.9 km, max 67.5 km | | |

**TESS sample.** 20 stations, 21 sites, 16 pixels in the raster: 15 in Spain (Extremadura town sites), 1 in Portugal (Porto). Only 4 pixels are as dark as the ranked spots (observed ≥ 20.5).

**Ground-truth corrections (2026-10-08).** Three measured sites had wrong coordinates and were corrected from OSM features/official coordinates: Cumeada observatory (~14 km off), Porta do Mezio (~20 km off; the old point is Gerês town), Monsaraz castle (~1 km off). "Alqueva Lake (eastern shore)" (38.20, −7.80) is Vidigueira town, ~25 km from the lake shore; it is excluded.

---

## 15. Limitations

1. 500 m pixels: mixed pixels at urban fringes.
2. Single-layer PSF: no aerosol profiles, humidity or wavelength dependence; one fitted scale factor.
3. Static emission (annual composite averages over the night).
4. Hansen canopy is the year-2000 baseline, partly corrected by loss years.
5. ERA5 at 0.25° does not resolve valley fog or orographic cloud.
6. Three years of VIIRS do not establish trends.
7. Candidate features are OSM nodes only (areas mapped as ways/relations are not candidates).
8. Access threshold rests on 18 official observation points; the stock OSRM profile excludes tracks.
9. Primary validation rests on 16 TESS pixels, 15 of them Spanish town sites and 1 in Porto; only 4 are as dark as the ranked spots. TESS-W and SQM passbands differ; no conversion is applied.
10. The selection keeps the upper SSI class per region; with unimodal distributions this is close to the top half and is not tied to an observed quality level.

---

## 16. References

- Duriscoe, D.M., Anderson, S.J., Luginbuhl, C.B. & Baugh, K.E. (2018). A simplified model of all-sky artificial sky glow derived from VIIRS Day/Night band data. JQSRT 214, 133-145.
- Falchi, F. et al. (2016). The new world atlas of artificial night sky brightness. Science Advances 2(6), e1600377.
- Hansen, M.C. et al. (2013). High-resolution global maps of 21st-century forest cover change. Science 342(6160), 850-853.
- Hersbach, H. et al. (2020). The ERA5 global reanalysis. QJRMS 146, 1999-2049.
- Horn, B.K.P. (1981). Hill shading and the reflectance map. Proc. IEEE 69(1), 14-47.
- Otsu, N. (1979). A threshold selection method from gray-level histograms. IEEE Trans. SMC 9(1), 62-66.
- Walker, M.F. (1977). The effects of urban lighting on the brightness of the night sky. PASP 89, 405-409.
