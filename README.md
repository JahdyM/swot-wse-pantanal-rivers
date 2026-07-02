# Multi-product validation of SWOT water surface elevation in the Pantanal Rivers

This repository contains the reproducible processing and analysis pipeline linked to the manuscript:

**Multi-product validation of SWOT water surface elevation in the Pantanal Rivers**

Jahdy Moreno-Oliveira a,b*, Alice Fassoni-Andrade b, Mark A. Trigg c, Daniel Medeiros Moreira d, Evlyn Marcia Leão de Moraes Novoa

a National Institute for Space Research (INPE), São Jose dos Campos, Brazil  
b Institute of Geosciences, University of Brasília (UnB), Brasília, Brazil  
c School of Civil Engineering, University of Leeds, Leeds, United Kingdom  
d Geological Survey of Brazil, Rio de Janeiro, Brazil

The repository supports the main methodology used in the article: in situ data harmonization, SWOT product time-series preparation, DAHITI/HydroWeb consolidation, quality control, Hampel outlier filtering, temporal matching, absolute validation, dynamic validation, and final table/figure export.

## Main Files

- `scripts/swot_wse_final_pipeline.ipynb`: short execution notebook.
- `scripts/swot_wse_pipeline.py`: reusable Python functions and the source of truth for the final pipeline.
- `requirements.txt`: Python dependencies.

## Generic Input Contract

Recommended public repository layout:

```text
<project-root>/
├── data/
│   ├── in_situ/
│   │   ├── unleveled/{station_id}.csv
│   │   └── gnss_leveled/{station_id}_leveled.csv
│   ├── metadata/station_metadata.csv
│   ├── masks/water_mask.shp
│   ├── vectors/gauge_locations.gpkg
│   └── altimetry/altimetry_station_codes.csv
├── outputs/
│   ├── swot_timeseries/
│   ├── altimetry_timeseries/
│   ├── tables/
│   └── figures/
└── scripts/
    ├── swot_wse_pipeline.py
    └── swot_wse_final_pipeline.ipynb
```

Paths are explicit in the notebook configuration. If your local data use a different directory layout, update the configuration cell directly.

## Required Inputs

### In Situ Time Series

Recommended files:

- Unleveled series: `data/in_situ/unleveled/{station_id}.csv`
- GNSS-leveled series: `data/in_situ/gnss_leveled/{station_id}_leveled.csv`

Required columns:

- `data`, `date`, or another parseable date/time column.
- One water-level column in meters: `wse`, `wse_ana`, `wse_egm08`, `Cota`, `cota`, `nivel`, or `stage`.

Optional column:

- `hydro_phase`, `phase`, `fase`, or `fase_hidrologica`.

If the hydrological phase column is missing, the pipeline infers phases from the in situ WSE series.

### Station Metadata

Recommended file:

- `data/metadata/station_metadata.csv`

Recommended columns:

- `station` or station-code aliases such as `codigo`, `cod_ana`, or `codigo_ana`
- `station_name`
- `river`
- `latitude`
- `longitude`
- `width`
- `drainage_area`
- `subregion`
- `pantanal`

### Water Mask

Recommended file:

- `data/masks/water_mask.shp`

Required column:

- `Codigo` or the configured station identifier.

### Gauge Locations

Recommended file:

- `data/vectors/gauge_locations.gpkg`

Required column:

- `Codigo` or the configured station identifier.

### DAHITI and HydroWeb Station Codes

Recommended file:

- `data/altimetry/altimetry_station_codes.csv`

Required columns:

- `cod_ana`
- `cod_dahiti`
- `cod_hidroweb`

Multiple DAHITI or HydroWeb codes can be separated by commas.

## Credentials

Use environment variables. Do not store keys in the notebook or in Git.

```bash
export DAHITI_API_KEY="your-key"
export HYDROWEB_API_KEY="your-key"
```

For SWOT downloads, configure the Earthdata Login used by `earthaccess`.

## Execution

1. Install dependencies if needed:

```bash
pip install -r requirements.txt
```

If you copied only the notebook to another virtual environment, use the commented installation cell at the top of the notebook instead. It lists the required packages directly and does not require `requirements.txt`.

2. Open the notebook:

```bash
jupyter lab scripts/swot_wse_final_pipeline.ipynb
```

The notebook can run as a standalone file. If `swot_wse_pipeline.py` is not present next to it, the bootstrap cell recreates that module in the current working directory.

3. Review the configuration cell.

Downloads are disabled by default:

```python
run_swot_downloads = False
run_altimetry_downloads = False
```

Turn them on only when credentials, input masks, and disk space are ready.

To reproduce the same final results obtained so far, keep the same input files and the same parameters:

- `date_start`
- `date_end`
- `calval_cutoff_date`
- `match_window_days`
- quality filters and Hampel-filter settings in `scripts/swot_wse_pipeline.py`

## Main Outputs

Tables:

- `outputs/tables/matchups_raw.csv`
- `outputs/tables/matchups_quality_filtered.csv`
- `outputs/tables/matchups_outlier_filtered.csv`
- `outputs/tables/metrics_absolute_overall.csv`
- `outputs/tables/metrics_overall.csv`
- `outputs/tables/metrics_absolute_by_station.csv`
- `outputs/tables/metrics_by_station.csv`
- `outputs/tables/metrics_by_product_orbital_phase.csv`
- `outputs/tables/error_by_hydrological_phase.csv`
- `outputs/tables/metrics_absolute_by_hydro_phase.csv`
- `outputs/tables/metrics_dynamic_by_station.csv`
- `outputs/tables/metrics_dynamic_overall.csv`
- `outputs/tables/outlier_filter_audit.csv`
- `outputs/tables/execution_summary.json`

Figures:

- `outputs/figures/fig_absolute_product_metrics.png`
- `outputs/figures/fig_dynamic_spearman_summary.png`
- `outputs/figures/fig_station_diagnostic_*.png`
- `outputs/figures/fig_hampel_outlier_audit.png`

## Method Summary

- SWOT products are searched and processed by time range and water-mask geometry.
- Each product is intersected with the station water mask.
- PIXC uses water-classified pixels and geophysical corrections to estimate WSE.
- Raster uses spatial clipping, quality flags, and WSE averaging.
- Node/Reach uses vector intersection and the closest valid river feature to the gauge.
- DAHITI/HydroWeb series are standardized to `date,wse,wse_u` and consolidated by the source with the largest number of post-filter observations.
- Absolute validation uses GNSS-leveled stations.
- Dynamic validation uses min-max normalized time series to compare temporal variability.
- Outlier handling uses a Hampel filter based on rolling median and MAD.
- Temporal matching uses the nearest observation within a 3-day window without reusing satellite observations.
