# Methodology

**Pipeline version:** 0.7.0
**Output:** 658 spots (SSI >= 65), Portugal (mainland + Madeira + Azores)

---

## 1. Data Acquisition

### VIIRS VNP46A4

| Parameter | Value |
|-----------|-------|
| Product | VNP46A4v001 (Black Marble annual) |
| Variable | `NearNadir_Composite_Snow_Free` |
| Resolution | 500m |
| Units | nW/cm^2/sr |
| Temporal span | 2023, 2024, 2025 |
| Tiles | h15v05, h16v05, h17v04, h17v05 |

Quality flags 1 (poor) and 255 (fill) excluded at ingestion. Gap-filled pixels use KDTree nearest-neighbor interpolation from independently-parsed HDF-EOS5 tiles.

### OpenStreetMap

Candidate features (`osm_extract.py`): nodes tagged with `enrichment.DEFAULT_OSM_TAGS` (peaks, hills, viewpoints, picnic sites, shelters, observatories, ...) from the Geofabrik Portugal extract, clipped to the Portugal land boundary (union of the 308 OSM municipalities, `scripts/build_boundary.py`). Replaces the one-off Overpass export of 2026-05-04 (10,898 nodes, incl. one peak in Colombia); the 2026-10-06 extract gives 10,931 nodes, 10,669 identical. The same extract feeds the access-point step, so one OSM snapshot drives the run.

---

## 2. Temporal Compositing

Per-pixel statistics from the 3-year stack:

```
R_median(x,y) = median(R_2023, R_2024, R_2025)
sigma(x,y) = std(R_2023, R_2024, R_2025)
trend(x,y) = (R_2025 - R_2023) / 2  [nW/cm^2/sr per year]
```

Median suppresses transient anomalies. Stability feeds confidence scoring. Trend feeds change detection.

---

## 3. Dark-Sky Classification

Threshold: **3.0 nW/cm^2/sr** (Bortle 3-4 boundary, Falchi et al. 2016). Conservative relative to data-driven optima (4.0-5.0 nW).

Per-pixel confidence:
```
C = 0.40 * C_distance + 0.30 * C_stability + 0.30 * C_consistency
```

- `C_distance`: sigmoid around threshold
- `C_stability`: 1 - sigma/sigma_max
- `C_consistency`: years_dark / 3

---

## 4. PSF Skyglow Propagation

```
PSF(d) = (d + d_0)^(-2.5) * exp(-beta * d)
```

| Parameter | Value | Source |
|-----------|-------|--------|
| d_0 | 1 km | Duriscoe (2018) |
| beta | 0.0187 km^-1 | Atmospheric extinction |
| Exponent | -2.5 | Walker (1977), Cinzano (2001) |
| Radius | 200 km | |
| CALIB_FACTOR | 0.04237 | Origin not reproducible (see §14); leave-one-out check in `scripts/fit_calibration.py` |

SQM conversion:
```
SQM = -2.5 * log10((B_artificial + 0.171) / 108000)
```

B_natural = 0.171 mcd/m^2 (Walker 1988). The model predicts clear-sky potential.

---

## 5. Cloud Climatology

ERA5 hourly total cloud cover (TCC), 0.25°, 2006-2025, all regions. Per grid cell:
```
clear_night_fraction = (dark hours with TCC < 0.2) / (dark hours)
```
Dark: Sun altitude < -18° at the cell's latitude and longitude at each hour (NOAA solar position equations; within 0.6° of Skyfield/DE421 in the tests). The 0.2 threshold is a design choice. Bilinear interpolation to the VIIRS grid.

---

## 6. Sky View Factor

Terrain SVF from Copernicus DEM GLO-30 (16 azimuth rays, 1.5km radius):
```
terrain_SVF = 1 - mean(sin(max_horizon_angle_i))
```

Vegetation-aware correction using Hansen GFC canopy cover:
```
effective_SVF = terrain_SVF * (1 - canopy_fraction)
```

Hard filter: effective_SVF > 0.7.

---

## 7. Land Cover

ESA WorldCover 10m provides base class. Tree pixels (code 10) receive probabilistic scoring from Hansen continuous canopy:
```
score = 1 - canopy_fraction
```

| Class | Score |
|-------|-------|
| Grassland, bare/sparse | 1.0 |
| Shrubland, moss/lichen | 0.8 |
| Cropland | 0.6 |
| Built-up, water, mangroves | 0.0 (excluded) |

---

## 8. Terrain Slope

Horn (1981) method from Copernicus DEM. Scoring:

| Slope | Score |
|-------|-------|
| 0-5 deg | 1.0 |
| 5-15 deg | 0.8 |
| 15-25 deg | 0.5 |
| 25+ deg | 0.2 |

Elevation normalized linearly to [0, 1] over 0-1500m.

---

## 9. SSI Computation

Weighted Linear Combination:
```
SSI = 100 * SUM(w_i * s_i)
```

| Factor | Weight |
|--------|--------|
| Darkness (SQM) | 0.30 |
| Clear sky | 0.25 |
| Sky openness (SVF) | 0.15 |
| Land cover | 0.15 |
| Slope | 0.10 |
| Elevation | 0.05 |

Thresholds: excellent >= 80, good >= 65, acceptable >= 50, marginal >= 35.

Only SSI >= 65 retained in output.

---

## 10. Spatial Filtering

- **Deduplication:** 1km minimum separation, keep highest SSI
- **Density cap:** Max 5 spots per 0.25-degree cell

---

## 11. Tiering and Access

**Destination tier:** viewpoints, campsites, picnic sites, nature reserves with facilities.
**Candidate tier:** peaks, ridgelines, unnamed clearings.

Tag-based access hints (`access_check.py`): drive_up / short_walk / hike_required / boat_required from the OSM feature type, with private/gated features excluded. These are heuristics, not measurements.

### Drivable access points (`access_points.py`)

Each spot gets the nearest point on a road a car can legally use **and stop on**, measured on the local OSM extract (`make download-osm`, Geofabrik, replication timestamp recorded in the output):

- **Drivable road:** OSRM car profile (`profiles/car.lua` @214ba8f, 2026-09-27) reproduced in Python: speed-table highway types, access hierarchy motorcar > motor_vehicle > vehicle > access, OSRM white/blacklists, blocked ways, vehicle dimensions. No `highway=track` (no speed in the stock profile).
- **Legal stopping:** Código da Estrada art. 72.º n.º 2 b) and art. 75.º (text as amended by Lei 72/2013) forbid stopping on motorways, their accesses and *vias reservadas a automóveis e motociclos* → `motorway`, `motorway_link`, `motorroad=yes` excluded.
- **Public access:** of OSRM's restricted values only `destination` is accepted.
- **Threshold:** `MAX_WALK_M = 358 m` = the largest road distance among the 18 official observation points in `validation/portugal/official_observation_points.csv` (median 22 m). No official site is farther from a drivable road. Reproduce with `scripts/derive_access_thresholds.py`.

Spots beyond the threshold get `access_kind = "none"` and are not offered as drive-to destinations. Output fields: `access_kind`, `access_lat/lon` (road point), `access_walk_m`, `access_climb_m` (net climb from Copernicus GLO-30, informational: DSM includes trees/structures), `access_road_type`.

Result (current output, OSM extract timestamp 2026-10-06T20:21:06Z): 316 of 658 spots accessible (mainland 231/542, Madeira 26/37, Azores 59/79); walk median 67.5 m. Guide coverage (3 nearest accessible spots, ≥15 km apart, search ≤150 km, over 4,264 OSM cities/towns/villages: 99.7 % get 3 spots; farthest of the 3 median 26 km, max 98 km; Flores/Corvo get 1) was computed outside this repository on an earlier spot set (320 accessible; mainland 555, Madeira 35, Azores 68) and is not reproducible here.

---

## 12. Change Detection

```
delta_R = R_2025 - R_2023
```

Significant when |delta_R| >= 1.0 nW/cm^2/sr (~0.3-0.4 mag, approximately one Bortle class).

---

## 13. Export Formats

| Format | Use Case |
|--------|----------|
| GeoJSON | Web applications, API |
| GeoParquet | Analytical queries |
| Cloud Optimized GeoTIFF | Cloud-native raster access |
| STAC Catalog | Discovery, provenance |

---

## 14. Validation Summary

Run with `make validate` (`scripts/run_validation.py`) and `scripts/fit_calibration.py`. Results on 2026-11-16; full tables in [validation_report.md](validation_report.md).

| Role | Source | N | MAE (mag) | Bias (mag) | Pearson r |
|------|--------|---|-----------|------------|-----------|
| Primary | TESS clear-sky (KDE mode), current CALIB_FACTOR | 16 pixels | 0.683 | +0.552 | 0.736 |
| Primary | TESS clear-sky, leave-one-out refit | 16 pixels | 0.593 | +0.130 | 0.712 |
| Indicative | Published SQM passing the audit | 2 | 0.191 | +0.191 | -- |
| Descriptive | Official observation points to nearest spot | 18 | median 4.2 km, max 31.9 km | | |

**TESS sample.** 20 stations → 21 sites → 16 pixels in the raster; 15 in Spain (Extremadura town sites), 1 in Portugal (Porto). Only 4 pixels are as dark as the ranked spots (observed ≥ 20.5).

**Calibration.** `CALIB_FACTOR = 0.04237` was documented as fitted to 27 ground-truth points (MAE 0.48 mag); no fitting code or point list is in the repository. A least-squares refit on the TESS pixels gives 0.0747 (1.76×); leave-one-out MAE 0.593 mag. The constant is not changed, so published spots stay reproducible.

**Reproducibility history.** The report shipped with the first commit (dated 2026-05-09: published-site MAE 0.286, TESS n=8 MAE 0.268, grid MAE 0.473, r = 0.937) cannot be reproduced with the code in this repository. Until 2026-10-08 `validate.py` pointed at a non-existent directory (`validation/portugal/portugal`), so every source was silently skipped, and `make validate` failed with an IndentationError. The 2026-10-08 figures (published MAE 0.620 over 7 sites, TESS best-night max n=20 MAE 0.739, grid r = 0.949) used sources since excluded or replaced: 5 of 7 published sites failed the audit, and the TESS clear-sky file was never written: that run stopped after 5 of 20 stations, and the same step reached 13 GB RSS when rerun (computed in chunks since 2026-11-16).

**Ground-truth corrections (2026-10-08).** Three measured sites had wrong coordinates and were corrected from OSM features/official coordinates: Cumeada observatory (~14 km off), Porta do Mezio (~20 km off; the old point is Gerês town), Monsaraz castle (~1 km off). "Alqueva Lake (eastern shore)" (38.20, −7.80) is Vidigueira town, ~25 km from the lake shore; its true location is unknown and it is excluded.

Systematic uncertainty: +/-0.5 mag vs full Garstang RT (single-scatter PSF omits multiple scattering, non-isotropic emission, variable aerosols).

---

## 15. Limitations

1. 500m pixel resolution: mixed pixels at urban fringes
2. Single-layer PSF omits aerosol profiles, humidity, wavelength dependence
3. Static emission assumption (annual composite averages diurnal modulation)
4. Hansen canopy is year-2000 baseline (partially corrected by loss years)
5. ERA5 at 25km for islands cannot resolve orographic effects
6. 3-year stack insufficient for trend significance
7. No spectral analysis (panchromatic DNB)
8. Density-cap grid origin depends on the data (`spots.geometry.y.min()` / `.x.min()`): adding or removing one edge spot shifts every 0.25° cell. Re-running on the 2026-10-06 OSM extract swapped 103 of 658 spots with identical SSI for the 555 kept.
9. Candidate features are OSM nodes only (areas mapped as ways/relations are not candidates).
10. Access threshold rests on 18 official observation points; drive times in the guide come from the public OSRM server (FOSSGIS profile, which routes tracks) while access points use the stock profile (no tracks).
11. Primary validation rests on 16 TESS pixels, 15 of them Spanish town sites and 1 in Porto; only 4 are as dark as the ranked spots. TESS-W and SQM passbands differ; no conversion is applied.

---

## 16. References

- Aksaker, N. et al. (2020). MNRAS 493(1), 1204-1216.
- Cinzano, P., Falchi, F. & Elvidge, C.D. (2001). MNRAS 328(3), 689-707.
- Duriscoe, D.M. (2018). JQSRT 212, 133-145.
- Falchi, F. et al. (2016). Science Advances 2(6), e1600377.
- Garstang, R.H. (1986). PASP 98, 364-375.
- Hansen, M.C. et al. (2013). Science 342(6160), 850-853.
- Kyba, C.C.M. et al. (2017). Science Advances 3(11), e1701528.
- Walker, M.F. (1988). PASP 100, 496-505.
