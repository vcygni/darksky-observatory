# Validation Report

Generated 2026-11-16 from `apps/stargazing_spots/output/portugal/validation_report.json`
(`make validate`) and `validation/portugal/calibration_loo.json`
(`scripts/fit_calibration.py`). Model: PSF skyglow, `CALIB_FACTOR = 0.04237`, 658 spots.
Notebook `notebooks/portugal/03_validation.ipynb` displays the same files.

| Role | Source | N | Used for |
|------|--------|---|----------|
| Primary | TESS photometers, clear-sky moonless zenith | 16 pixels | accuracy |
| Indicative | Published SQM sites passing the audit | 2 | reported separately, not a baseline |
| Descriptive | Official observation points | 18 | distance to nearest spot |

No MAE is pooled across sources.

## Primary: TESS clear-sky (16 pixels)

Observed value: mode of the dark (Sun < −18°), moonless (Moon < 0°) readings per
site, from `scripts/derive_tess_clear_sky.py`. Sites sharing a model pixel are
averaged.

| Metric | vs KDE mode | vs median (sensitivity) |
|--------|-------------|-------------------------|
| MAE (mag) | 0.683 | 0.779 |
| Bias, predicted − observed (mag) | +0.552 | +0.730 |
| RMSE (mag) | 0.857 | 0.939 |
| Max abs error (mag) | 2.375 | 2.401 |
| Pearson r | 0.736 | 0.793 |
| Spearman ρ | 0.603 | 0.609 |

Positive bias: the model predicts darker skies than TESS measures at 14 of 16 pixels.

**Sample.** 20 stations → 21 sites (stars218 moved) → 16 pixels inside the raster.
Outside the raster: stars218 (one of its two positions), stars384, stars387. stars66
has no usable file (all 38 marked uncalibrated by the supplier). 15 pixels are in
Spain (Extremadura, mostly town halls and cultural centres); 1 is in Portugal
(Porto, stars40 + stars41 on one building).

| Largest errors | Observed | Predicted | Error |
|----------------|----------|-----------|-------|
| Olivenza (stars271; two location names at one position) | 19.28 | 21.65 | +2.38 |
| San Benito de la Contienda (stars332) | 20.43 | 21.47 | +1.04 |
| Alconchel (stars320) | 19.41 | 20.43 | +1.02 |
| Porto (stars40/41) | 18.21 | 17.52 | −0.68 |

## Calibration check

`CALIB_FACTOR` is the model's only free scale. The previous documentation said it was
fitted to 27 ground-truth points (MAE 0.48 mag); no fitting code or point list for
that fit is in the repository. `scripts/fit_calibration.py` refits it on the TESS
pixels and estimates held-out error by leave-one-out (fit on 15, predict the 16th).

| | CALIB_FACTOR | MAE | Bias | RMSE | Pearson r |
|---|---|---|---|---|---|
| Current constant | 0.04237 | 0.683 | +0.552 | 0.857 | 0.736 |
| In-sample fit | 0.07467 | 0.555 | +0.139 | 0.755 | 0.722 |
| Leave-one-out | 0.0676–0.0876 | **0.593** | +0.130 | 0.798 | 0.712 |

The leave-one-out MAE (0.593 mag) is the estimate of error at an unseen site. The
refit factor is 1.76× the current one; it is **not** adopted, because it would change
every published spot. Restricted to the 4 pixels as dark as the spots being ranked
(observed ≥ 20.5): MAE 0.522 / bias +0.341 with the current constant, 0.451 / +0.008
leave-one-out.

## Indicative: published SQM (2 sites)

| Site | Published | Predicted |
|------|-----------|-----------|
| Dark Sky Alqueva Observatory (Cumeada) | 21.43 | 21.649 |
| Peneda-Gerês (Porta do Mezio) | 21.30 | 21.463 |

MAE 0.191, bias +0.191 mag. The other 5 measured sites are excluded:
`validation/portugal/published_sites_audit.csv` gives the reason for each
(unverifiable value or certification, wrong or unknown coordinates).

## Descriptive: official observation points

Distance from each of 18 official/public observation points to the nearest pipeline
spot: median 4.2 km, max 31.9 km.

## Retired figures

| Earlier claim | Status |
|---------------|--------|
| "4 independent sources (1,935 points)", cross-source MAE 0.342 | pooled a VIIRS-based model (1,920 points) with 15 observations; not reproducible |
| Published SQM MAE 0.286 (7 sites) | from a model version not in the repository; 5 of 7 sites fail the audit |
| TESS MAE 0.268 (8 stations, best-night max) | best-night maximum is not the clear-sky value the model predicts; replaced by the KDE mode |
| SSI weight robustness (Spearman ρ > 0.97) and 14 flagged spots | no code in the repository produces them; removed |

## Limitations

1. The TESS sample is 15 Spanish town sites and 1 Porto building. Only 4 pixels are
   in the darkness range of the ranked spots (predicted SQM 20.56–22.06).
2. The model has 500 m pixels; a photometer on a town building also sees local lights
   that the pixel average does not resolve.
3. TESS-W and SQM have different passbands; no conversion is applied.
4. Temporal mismatch: TESS readings 2019–2025, VIIRS composite 2023–2025.
5. Single-scatter PSF: ±0.5 mag systematic uncertainty against full radiative transfer.
6. Raw TESS files (732 MB) are not in the repository; `tess_clear_sky.json` is, with
   the derivation script and log.
