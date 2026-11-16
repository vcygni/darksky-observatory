# TESS-IDA Validation Data

TESS-W photometers of the Stars4All network: 20 stations, monthly `.dat` files 2019–2025.
By the position in each file's header, 21 sites (stars218 moved): **19 in Spain**
(mostly Extremadura) and **2 in Portugal** (stars40, stars41 on one Porto building).

## Pipeline usage

`stargazing_spots/validate.py` reads `tess_clear_sky.json` as the primary validation
source. It is produced from the raw files by `scripts/derive_tess_clear_sky.py`
(log: `derive_tess_clear_sky.log`): per site, the mode of the readings taken with the
Sun below −18° and the Moon below the horizon. The raw `.dat` files and SQLite DB are
not in the repository and are not needed to run validation.

`tess_station_summary.json` is the earlier per-station summary (all-time median / P95,
one position per station). It is superseded and not read by any code; its positions
disagree with the file headers for several stations.

## Downloading raw data (optional)

To rerun `scripts/derive_tess_clear_sky.py` or analyse the raw readings:

1. Copy `.env.example` to `.env`
2. Request the IDA_URL from the Stars4All project (contact: rafael08@ucm.es or jzamorano@fis.ucm.es)
3. Download station directories via WebDAV:

```bash
cp .env.example .env
# Edit .env — set IDA_URL to the NextCloud shared link you receive

# Download a single station:
curl -O "${IDA_URL}/stars201/stars201_2023-07.dat"

# Or bulk-download all stations with wget:
wget -r -np -nH --cut-dirs=4 "${IDA_URL}"
```

The URL provides access to a NextCloud WebDAV share containing monthly `.dat` files per station.

## Sites (`tess_clear_sky.json`)

| Station | Location | Country | Lat | Lon | Dark+moonless nights | Clear-sky SQM (mode) |
|---|---|---|---|---|---|---|
| stars201 | Finca La Cocosa, Badajoz | Spain | 38.7555 | -6.9845 | 843 | 20.59 |
| stars218 | Alcazaba de la Reina, Extremadura | Spain | 38.1898 | -5.9571 | 381 | 21.16 |
| stars218 | La Roca de la Sierra, La Roca de la Sierra | Spain | 39.1095 | -6.6892 | 508 | 21.11 |
| stars271 | Olivenza, Olivenza | Spain | 38.7428 | -7.2100 | 292 | 18.91 |
| stars271 | Puerto Villareal, Olivenza | Spain | 38.7428 | -7.2100 | 313 | 19.64 |
| stars288 | Entre Encinas y Estrellas, Fregenal de la Sierra | Spain | 38.2197 | -6.6318 | 1683 | 21.15 |
| stars316 | Casa de la Cultura, Táliga | Spain | 38.5285 | -7.0165 | 233 | 20.89 |
| stars319 | Torreón, Zahínos | Spain | 38.3289 | -6.9517 | 211 | 20.24 |
| stars320 | Ayuntamiento, Alconchel | Spain | 38.5167 | -7.0708 | 160 | 19.41 |
| stars321 | Centro de formación Polivalente, Valle de Santa Ana | Spain | 38.3662 | -6.7892 | 216 | 20.14 |
| stars322 | Ayuntamiento, Barcarrota | Spain | 38.5141 | -6.8496 | 139 | 20.17 |
| stars323 | Centro Municipal Nertobriga, Fregenal de la Sierra | Spain | 38.1663 | -6.6561 | 213 | 19.87 |
| stars324 | Casa de la cultura, Cheles | Spain | 38.5112 | -7.2792 | 222 | 20.45 |
| stars325 | Residencia de mayores Virgen de Guadalupe, Olivenza | Spain | 38.6845 | -7.1059 | 181 | 19.89 |
| stars327 | Biblioteca Municipal "Cronista Andrés Bernáldez", Fuentes de León | Spain | 38.0682 | -6.5393 | 196 | 20.16 |
| stars328 | Ayuntamiento, Oliva de la Frontera | Spain | 38.2770 | -6.9198 | 116 | 20.04 |
| stars332 | Centro Cultural, San Benito de la Contienda | Spain | 38.6323 | -7.1578 | 203 | 20.43 |
| stars384 | Granadilla, Zarza de Granadilla | Spain | 40.2702 | -6.1042 | 64 | 20.93 |
| stars387 | Centro de Interpretación de Cáparra, Oliva de Plasencia | Spain | 40.1643 | -6.0994 | 180 | 21.21 |
| stars40 | Escola Superior de Saúde do Politécnico do Porto, Porto | Portugal | 41.1774 | -8.6060 | 1563 | 18.09 |
| stars41 | Escola Superior de Saúde do Politécnico do Porto, Porto | Portugal | 41.1774 | -8.6060 | 1575 | 18.32 |

Excluded files — marked uncalibrated by the supplier: stars218 13, stars271 3, stars322 1, stars66 38 (stars66 has no usable
file); no header position: stars201 23, stars271 4, stars288 5, stars384 15, stars387 3.

## File structure

```
tess-ida/
├── .env.example                # Template — needs IDA_URL from Stars4All
├── tess_clear_sky.json         # Clear-sky value per site (read by validate.py)
├── derive_tess_clear_sky.log   # Log of the run that produced it
├── tess_station_summary.json   # Superseded summary (not used)
├── README.md
├── adm/
│   └── tessida.db              # SQLite DB (not committed)
└── IDA/
    └── stars*/                 # Monthly .dat files (not committed)
```

## .dat format

IDA/NSBM standard: `#` header lines (location name, `Position: lat, lon, elevation`,
TESS zero point, calibration note), then one `;`-separated row per reading:

```
UTC Date & Time;Local Date & Time;Enclosure Temperature;Sky Temperature;Frequency;MSAS;ZP;Sequence Number
2019-01-27T17:42:30.000;2019-01-27T18:42:30.000;9.17;-23.7;50000.0;0.0;20.47;4720
```
