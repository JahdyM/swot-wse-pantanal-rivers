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

Edit the first configuration cell if your folders differ.

```text
<project-root>/
├── data/
│   ├── in_situ/
│   │   ├── unleveled/{station_id}.csv
│   │   └── gnss_leveled/{station_id}_leveled.csv
│   ├── metadata/station_metadata.csv
│   └── altimetry/altimetry_station_codes.csv
├── outputs/
│   ├── swot_timeseries/Station_{station_id}/
│   │   ├── pixc_complete_raw.csv
│   │   ├── raster_complete_raw.csv
│   │   ├── node_complete_raw.csv
│   │   └── reach_complete_raw.csv
│   ├── altimetry_timeseries/Station_{station_id}/alt_conv_{station_id}.csv
│   ├── tables/
│   └── figures/
└── scripts/swot_wse_final_pipeline.ipynb
```

## Required Inputs

Station metadata must contain a station-code column named `station`, `codigo`, `cod_ana`, `codigo_ana`, or `id`.

In situ CSV files must contain:

- a parseable date/time column
- a water-level column such as `wse`, `wse_ana`, `wse_egm08`, `Cota`, `cota`, `nivel`, or `stage`

SWOT product CSV files must contain:

- a parseable date/time column
- `wse_media` for PIXC/Raster or `wse` for Node/Reach

Altimetry CSV files must contain:

- a parseable date/time column
- `wse`

## Execution

Open and run:

```bash
jupyter lab scripts/swot_wse_final_pipeline.ipynb
```

No repository-specific package installation is required. If your Jupyter environment already has `matplotlib`, figures are exported automatically. If not, the notebook still produces CSV tables.

## Main Outputs

- `outputs/tables/matchups_raw.csv`
- `outputs/tables/matchups_quality_filtered.csv`
- `outputs/tables/matchups_outlier_filtered.csv`
- `outputs/tables/metrics_overall.csv`
- `outputs/tables/metrics_by_station.csv`
- `outputs/tables/metrics_by_product_orbital_phase.csv`
- `outputs/tables/error_by_hydrological_phase.csv`
- `outputs/tables/metrics_dynamic_by_station.csv`
- `outputs/tables/metrics_dynamic_overall.csv`
- `outputs/tables/outlier_filter_audit.csv`
- `outputs/tables/execution_summary.json`
- `outputs/figures/*.png` when `matplotlib` is available

## Method Summary

- Quality filtering is applied to the available product quality columns.
- Outliers are flagged with a Hampel filter based on rolling median and MAD.
- In situ and satellite/altimetry observations are matched by nearest date within a 3-day window without reusing satellite observations.
- Absolute validation uses GNSS-leveled stations.
- Dynamic validation uses min-max normalized station-product time series.
