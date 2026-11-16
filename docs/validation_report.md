# Validation Report

From `apps/stargazing_spots/output/portugal/validation_report.json` (`make validate`) and
`validation/portugal/calibration_loo.json` (`scripts/fit_calibration.py`), 2026-11-16.
Model: PSF skyglow, `CALIB_FACTOR = 0.07467`; 597 spots. `notebooks/portugal/03_validation.ipynb`
displays the same files.

| Role | Source | N |
|------|--------|---|
| Primary | TESS photometers, clear-sky moonless zenith | 16 pixels |
| Indicative | Published SQM sites that pass the audit | 2 |
| Descriptive | Official observation points | 18 |

No error is pooled across sources.

## Primary: TESS clear-sky (16 pixels)

Observed value per site: mode of the readings with the Sun below −18° and the Moon below
the horizon (`scripts/derive_tess_clear_sky.py`). Sites in the same model pixel are averaged.

| Metric | vs mode | vs median (sensitivity) |
|--------|---------|-------------------------|
| MAE (mag) | 0.555 | 0.584 |
| Bias, predicted − observed (mag) | +0.138 | +0.316 |
| RMSE (mag) | 0.755 | 0.742 |
| Max abs error (mag) | 2.168 | 2.194 |
| Pearson r | 0.722 | 0.779 |
| Spearman ρ | 0.603 | 0.609 |

These are in-sample: `CALIB_FACTOR` is fitted to the same pixels (next section).

**Sample.** 20 stations, 21 sites (stars218 moved), 16 pixels inside the raster.
Outside: stars218 (one of its two positions), stars384, stars387. stars66 has no usable
file (all 38 marked uncalibrated by the supplier). 15 pixels are in Spain (Extremadura,
mostly town halls and cultural centres), 1 in Portugal (Porto, stars40 + stars41).

| Largest errors | Observed | Predicted | Error |
|----------------|----------|-----------|-------|
| Olivenza (stars271; two location names at one position) | 19.28 | 21.44 | +2.17 |
| Porto (stars40/41) | 18.21 | 16.91 | −1.29 |
| La Roca de la Sierra (stars218) | 21.11 | 20.30 | −0.82 |
| San Benito de la Contienda (stars332) | 20.43 | 21.19 | +0.76 |

## Calibration

`CALIB_FACTOR` is the model's only free scale, fitted by least squares (error in mag) on the
16 pixels. Leave-one-out fits it on 15 pixels and predicts the 16th.

| | CALIB_FACTOR | MAE | Bias | RMSE | Pearson r |
|---|---|---|---|---|---|
| Fit (used) | 0.07467 | 0.555 | +0.139 | 0.755 | 0.722 |
| Leave-one-out | 0.0676–0.0876 | **0.593** | +0.130 | 0.798 | 0.712 |

The leave-one-out MAE (0.593 mag) is the accuracy estimate for an unseen site. On the 4
pixels as dark as the ranked spots (observed ≥ 20.5): MAE 0.426, bias +0.018 (fit); 0.451,
+0.008 (leave-one-out).

## Indicative: published SQM (2 sites)

| Site | Published | Predicted |
|------|-----------|-----------|
| Dark Sky Alqueva Observatory (Cumeada) | 21.43 | 21.44 |
| Peneda-Gerês (Porta do Mezio) | 21.30 | 21.18 |

MAE 0.066, bias −0.055 mag. Per-site value and position cannot be verified, so these are
not a baseline. The other 5 measured sites are excluded; reasons in
`validation/portugal/published_sites_audit.csv`.

## Descriptive: official observation points

Distance from each of the 18 official observation points to the nearest output spot:
median 5.9 km, max 67.5 km.

## Earlier figures

| Earlier claim | Status |
|---------------|--------|
| "4 independent sources (1,935 points)", r = 0.937 / 0.949 | pooled 15 observations with 1,920 points of another VIIRS-driven model (darkskysites.com), now removed |
| Published SQM MAE 0.286 (7 sites) | from a model version not in the repository; 5 of 7 sites fail the audit |
| TESS MAE 0.268 (8 stations) | best-night maximum, not the clear-sky value the model predicts |
| `CALIB_FACTOR = 0.04237` "fitted to 27 points, MAE 0.48" | no fitting code or point list in the repository; TESS MAE 0.683, bias +0.552 |
| SSI weight robustness and 14 flagged spots | no code in the repository produces them |

## Limitations

1. 15 of the 16 TESS pixels are Spanish town sites and 1 is in Porto; only 4 are as dark as
   the ranked spots.
2. 500 m pixels; a photometer on a town building also sees local lights the pixel average
   does not resolve.
3. TESS-W and SQM passbands differ; no conversion is applied.
4. TESS readings 2019–2025, VIIRS composite 2023–2025.
5. Raw TESS files (732 MB) are not in the repository; `tess_clear_sky.json`, its script and
   log are.
