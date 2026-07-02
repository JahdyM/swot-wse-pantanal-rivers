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

## Column and Date Formats

- Preferred date/time format: ISO `YYYY-MM-DD` or `YYYY-MM-DD HH:MM:SS`. SWOT filename/date columns may also contain a `YYYYMMDDTHHMMSS` token, for example `SWOT_L2_20240415T123456_...nc`.
- Also accepted when unambiguous: `YYYY/MM/DD`, `YYYYMMDD`, `DD/MM/YYYY`, `DD-MM-YYYY`, Unix timestamps, and Excel serial dates. Avoid ambiguous `MM/DD/YYYY` dates.
- Date/time values are treated as timezone-naive after parsing. Use one time basis consistently across all input tables.
- Water-surface elevation values must be numeric and in meters. Decimal points are preferred; decimal commas are accepted when the rest of the value is numeric.
- Missing numeric values should be blank or standard missing-value tokens such as `NaN`, `NA`, or `null`.
- Station identifiers should be stored as text or integer-like values without changing leading/significant digits.

| CSV type | Required date columns | Required WSE columns | Optional columns used | Notes |
|---|---|---|---|---|
| Station metadata | not required | not required | `station_name`, `river`, `latitude`, `longitude`, `width`, `drainage_area`, `subregion`, `pantanal` | Must include `station`, `station_id`, `gauge_id`, `codigo`, `cod_ana`, `codigo_ana`, or `id`. |
| In situ raw/unleveled | `data`, `date`, `datetime`, `data_ref`, or `time` | `wse_ana`, `Cota`, `cota`, `wse`, `WSE`, `wse_egm08`, `nivel`, or `stage` | hydrological phase columns | Used for dynamic validation or fallback. |
| In situ GNSS-leveled | `data`, `date`, `datetime`, `data_ref`, or `time` | `wse_swot_ref`, `wse_ana`, `wse_egm08`, `Cota`, `cota`, `wse`, `WSE`, `nivel`, or `stage` | hydrological phase columns | Used for absolute validation. |
| SWOT PIXC | `data`, `date`, `datetime`, `arquivo`, or `filename` | `wse_media`, `wse`, `WSE`, `height_media`, `height`, or `height_mean` | source filename columns | Filename dates should include `YYYYMMDDTHHMMSS`. |
| SWOT Raster | `data`, `date`, `datetime`, `arquivo`, or `filename` | `wse_media`, `wse`, `WSE`, `height`, or `height_mean` | `wse_qual_media` | Rows with `wse_qual_media >= 1.8` are removed when present. |
| SWOT Node | `data`, `date`, `datetime`, `time_str`, `timestamp_arquivo`, `arquivo_origem`, or `arquivo` | `wse`, `WSE`, or `wse_sm` | `node_q` | Quality filtering uses `node_q` when present. |
| SWOT Reach | `data`, `date`, `datetime`, `time_str`, `timestamp_arquivo`, `arquivo_origem`, or `arquivo` | `wse` or `WSE` | `reach_q` | Quality filtering uses `reach_q` when present. |
| External altimetry | `date`, `data`, `datetime`, or `time` | `wse`, `WSE`, `water_level`, `height`, or `altura` | none required | Multiple rows on the same date are averaged before matchup. |

Minimal CSV header examples:

```text
station_metadata.csv: station,station_name,river,latitude,longitude,width,drainage_area
in_situ/{station_id}.csv: data,wse
in_situ_leveled/{station_id}_leveled.csv: data,wse_swot_ref
swot_pixc_timeseries.csv: data,wse_media
swot_raster_timeseries.csv: data,wse_media,wse_qual_media
swot_node_timeseries.csv: time_str,wse,node_q
swot_reach_timeseries.csv: time_str,wse,reach_q
external_altimetry_timeseries.csv: date,wse
```

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
