# Data Sources

## Dataset Inventory

| Dataset | Provider | Product | Resolution | Access |
|---------|----------|---------|-----------|--------|
| Nighttime Lights | NASA LP DAAC | VNP46A4v001 | 500m annual | Earthdata Login (free) |
| Cloud | ECMWF / C3S | ERA5 hourly TCC | 0.25 deg | DestinE Earth Data Hub (free account) |
| Elevation | ESA / Copernicus | GLO-30 DEM | 30m | AWS S3 (public) |
| Forest Canopy | U. Maryland | Hansen GFC v1.11 | 30m | GCS (public) |
| Land Cover | ESA | WorldCover v200 | 10m | AWS S3 (public) |
| Points of Interest | OpenStreetMap | Geofabrik Portugal extract | Vector | download.geofabrik.de |
| Land boundary | OpenStreetMap | admin_level=7 union | Vector | Geofabrik extract |
| Validation (TESS) | Stars4All / UCM | TESS-W monthly IDA files | Point | On request (see `validation/portugal/tess-ida/README.md`) |
| Validation (SQM) | Literature | Field measurements | Point | Papers |

## OSM Tags Queried

```
tourism = camp_site | viewpoint | picnic_site | wilderness_hut
natural = peak | hill | ridge | saddle | heath | grassland | bare_rock | scree | cliff
leisure = nature_reserve | picnic_site
amenity = shelter
man_made = observatory
landuse = meadow | grass
```

## Licensing

| Dataset | License | Commercial Use |
|---------|---------|----------------|
| NASA VIIRS | Public domain | Yes |
| Copernicus DEM | Copernicus Data Policy | Yes |
| ESA WorldCover | CC-BY 4.0 | Yes |
| Hansen GFC | CC-BY 4.0 | Yes |
| ERA5 (Earth Data Hub copy) | CC BY 4.0 | Yes (attribution) |
| OpenStreetMap (features, roads, boundary) | ODbL 1.0 | Yes (attribution, share-alike) |
| TESS photometer data | ODbL 1.0 (IDA file header) | Yes (attribution, share-alike) |

## Authentication

| Dataset | Registration URL |
|---------|-----------------|
| VIIRS VNP46A4 | https://urs.earthdata.nasa.gov/ |
| ERA5 | https://earthdatahub.destine.eu/ |

All other datasets are publicly accessible without authentication. The pipeline fetches them automatically on first run.
