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

Run the notebook from the same working directory used by the processing workflow. Edit the first configuration cell only if your folders differ.

```text
<working-directory>/
├── analises/
│   └── tabelas/
│       ├── ana_metadados.csv
│       └── correspondencia_altimetria_convencional.csv
├── dados_processados/
│   └── ana/
│       ├── sem_nivelamento/{station_id}.csv
│       └── nivelamento/{station_id}_nivelada.csv
├── analise_final/
│   ├── water_mask_15m.shp
│   └── Estacao_{station_id}/
│       ├── pixc_complete_raw.csv
│       ├── raster_complete_raw.csv
│       ├── node_complete_raw.csv
│       ├── reach_complete_raw.csv
│       └── alt_conv_{station_id}.csv
├── analysis_absolute/
├── analysis_temporal/
├── analysis_drivers/
└── figures/
    ├── main/
    └── supplementary/
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

Absolute validation tables are written to `analysis_absolute/`:

- `matchups_raw.csv`
- `matchups_quality_filtered.csv`
- `matchups_outlier_filtered.csv`
- `metrics_overall.csv`
- `metrics_by_station.csv`
- `metrics_by_product_orbital_phase.csv`
- `error_by_hydrological_phase.csv`
- `outlier_filter_audit.csv`
- `execution_summary.json`

Dynamic validation tables are written to `analysis_temporal/`:

- `matchups_raw.csv`
- `matchups_quality_filtered.csv`
- `matchups_outlier_filtered.csv`
- `metrics_dynamic_by_station.csv`
- `metrics_dynamic_overall.csv`
- `normalized_series_for_examples.csv`
- `outlier_filter_audit.csv`
- `execution_summary.json`

Figures are written to `figures/main/` when `matplotlib` is available.

## Method Summary

- Quality filtering is applied to the available product quality columns.
- Outliers are flagged with a Hampel filter based on rolling median and MAD.
- In situ and satellite/altimetry observations are matched by nearest date within a 3-day window without reusing satellite observations.
- Absolute validation uses GNSS-leveled stations.
- Dynamic validation uses min-max normalized station-product time series.
