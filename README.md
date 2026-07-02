# Multi-product validation of SWOT water surface elevation in the Pantanal Rivers

This repository contains a single-notebook workflow linked to a manuscript currently under submission and not yet published:

**Multi-product validation of SWOT water surface elevation in the Pantanal Rivers**

Jahdy Moreno-Oliveira a,b*, Alice Fassoni-Andrade b, Mark A. Trigg c, Daniel Medeiros Moreira d, Evlyn Marcia Leão de Moraes Novoa

a National Institute for Space Research (INPE), São Jose dos Campos, Brazil  
b Institute of Geosciences, University of Brasília (UnB), Brasília, Brazil  
c School of Civil Engineering, University of Leeds, Leeds, United Kingdom  
d Geological Survey of Brazil, Rio de Janeiro, Brazil

Manuscript status: under submission; not yet published.

## File

- `scripts/swot_wse_final_pipeline.ipynb`

The notebook is self-contained. It does not require a companion Python module. It uses Python standard-library modules for table reading, time-series matching, outlier filtering, and metric calculation. If `matplotlib` is already available, it also exports figures; otherwise, table outputs are still generated.

## Input Contract

Organize the analysis folder into a few logical data groups. The folder and file names below are generic examples; if your local names differ, update the first configuration cell so each key points to the correct location. The important rule is that the same `station_id` must be used consistently across metadata, in situ files, SWOT product tables, and altimetry tables.

```text
<analysis-root>/
├── metadata/
│   ├── station_metadata.csv
│   └── altimetry_station_codes.csv        # optional, only needed before external-data download
├── in_situ/
│   ├── raw_or_unleveled/
│   │   └── {station_id}.csv
│   └── gnss_leveled/
│       └── {station_id}_leveled.csv
├── satellite_timeseries/
│   └── {station_id}/
│       ├── swot_pixc_timeseries.csv
│       ├── swot_raster_timeseries.csv
│       ├── swot_node_timeseries.csv
│       ├── swot_reach_timeseries.csv
│       └── external_altimetry_timeseries.csv
└── results/
    ├── absolute_validation/
    ├── dynamic_validation/
    ├── driver_analysis/
    └── figures/
```

## Required Inputs

Station metadata must contain one row per gauge/station and a station identifier column such as `station`, `station_id`, `gauge_id`, `codigo`, `cod_ana`, `codigo_ana`, or `id`. Optional but useful columns include station name, river, latitude, longitude, river width, drainage area, Pantanal subregion, and land-cover percentages.

In situ CSV files must contain:

- a parseable date/time column
- a water-level column in meters, such as `wse`, `wse_ana`, `wse_egm08`, `Cota`, `cota`, `nivel`, or `stage`
- consistent `station_id` naming between raw/unleveled and GNSS-leveled files

SWOT product CSV files must contain:

- a parseable date/time column
- a WSE column in meters; PIXC/Raster usually use `wse_media` or `wse`, while Node/Reach usually use `wse` or `WSE`
- optional quality columns, which are used by the filters when available

Altimetry CSV files must contain:

- a parseable date/time column
- a WSE column in meters, usually named `wse`

Output folders can be empty before execution. The notebook creates CSV tables, diagnostics, and figures there.

## Execution

Open and run:

```bash
jupyter lab scripts/swot_wse_final_pipeline.ipynb
```

No repository-specific package installation is required. If your Jupyter environment already has `matplotlib`, figures are exported automatically. If not, the notebook still produces CSV tables.

## Main Outputs

Absolute validation tables are written to `analysis_absolute/`:

- `matchups_raw.csv`
- `matchups_quality_filtered.csv`
- `matchups_outlier_filtered.csv`
- `metrics_overall.csv`
- `metrics_by_station.csv`
- `metrics_by_product_orbital_phase.csv`
- `error_by_hydrological_phase.csv`
- `outlier_filter_audit.csv`
- `data_load_audit.csv`
- `pipeline_diagnostics.json`
- `execution_summary.json`

Dynamic validation tables are written to `analysis_temporal/`:

- `matchups_raw.csv`
- `matchups_quality_filtered.csv`
- `matchups_outlier_filtered.csv`
- `metrics_dynamic_by_station.csv`
- `metrics_dynamic_overall.csv`
- `normalized_series_for_examples.csv`
- `outlier_filter_audit.csv`
- `data_load_audit.csv`
- `pipeline_diagnostics.json`
- `execution_summary.json`

Driver-analysis support tables are written to `analysis_drivers/`.

Figures are written to `figures/main/` when `matplotlib` is available.

## Method Summary

- Quality filtering is applied to the available product quality columns.
- Outliers are flagged with a Hampel filter based on rolling median and MAD.
- In situ and satellite/altimetry observations are matched by nearest date within a 3-day window without reusing satellite observations.
- Absolute validation uses GNSS-leveled stations.
- Dynamic validation uses min-max normalized station-product time series from all stations with valid matchups.
- Absolute aggregate Spearman values use station-level Spearman means as the primary `spearman_r`, with pooled Spearman retained as an auxiliary column.
- The notebook writes loading and pipeline diagnostics before stopping if either absolute or dynamic matchups are empty.
