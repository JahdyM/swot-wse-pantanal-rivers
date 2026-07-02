from __future__ import annotations

import json
import os
import re
import shutil
import zipfile
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import scipy.stats as stats


PRODUCTS_SWOT = ["pixc", "raster", "node", "reach"]
PRODUCTS_ALL = PRODUCTS_SWOT + ["altimetry"]
PRODUCT_LABELS = {
    "pixc": "PIXC",
    "raster": "Raster",
    "node": "Node",
    "reach": "Reach",
    "altimetry": "Altimetry",
}
PRODUCT_COLORS = {
    "pixc": "#e67e22",
    "raster": "#2e7d32",
    "node": "#c0392b",
    "reach": "#6c5ce7",
    "altimetry": "#6f6f6f",
}
HYDRO_PHASE_ORDER = ["Low", "Rising", "High", "Falling"]


@dataclass
class PipelineConfig:
    project_root: Path = Path("..").resolve()
    in_situ_unleveled_dir: Path = Path("data/in_situ/unleveled")
    in_situ_gnss_leveled_dir: Path = Path("data/in_situ/gnss_leveled")
    metadata_file: Path = Path("data/metadata/station_metadata.csv")
    water_mask_file: Path = Path("data/masks/water_mask.shp")
    stations_vector_file: Path = Path("data/vectors/gauge_locations.gpkg")
    altimetry_codes_file: Path = Path("data/altimetry/altimetry_station_codes.csv")
    swot_station_dir_template: str = "outputs/swot_timeseries/Station_{station}"
    altimetry_station_dir_template: str = "outputs/altimetry_timeseries/Station_{station}"
    tables_dir: Path = Path("outputs/tables")
    figures_dir: Path = Path("outputs/figures")
    date_start: str = "2023-03-31"
    date_end: str = "2025-08-01"
    calval_cutoff_date: str = "2023-07-01"
    match_window_days: int = 3
    station_filter: tuple[str, ...] = tuple()
    hydroweb_bbox: tuple[float, float, float, float] = (
        -59.283966,
        -22.1041297,
        -54.9274659,
        -16.033635,
    )
    run_swot_downloads: bool = False
    run_altimetry_downloads: bool = False
    overwrite_outputs: bool = False


def paths(cfg: PipelineConfig) -> dict[str, Path]:
    root = Path(cfg.project_root).resolve()

    p = {
        "root": root,
        "in_situ_unleveled": root / cfg.in_situ_unleveled_dir,
        "in_situ_gnss_leveled": root / cfg.in_situ_gnss_leveled_dir,
        "metadata": root / cfg.metadata_file,
        "water_mask": root / cfg.water_mask_file,
        "stations_vector": root / cfg.stations_vector_file,
        "altimetry_codes": root / cfg.altimetry_codes_file,
        "tables": root / cfg.tables_dir,
        "figures": root / cfg.figures_dir,
    }
    for key in ["tables", "figures"]:
        p[key].mkdir(parents=True, exist_ok=True)
    return p


def station_dir(cfg: PipelineConfig, template: str, station: str) -> Path:
    return Path(cfg.project_root).resolve() / template.format(station=normalize_station_id(station))


def config_as_json(cfg: PipelineConfig) -> str:
    return json.dumps({k: str(v) for k, v in asdict(cfg).items()}, indent=2, ensure_ascii=False)


def validate_inputs(cfg: PipelineConfig, strict: bool = False) -> pd.DataFrame:
    p = paths(cfg)
    required = [
        "metadata",
        "water_mask",
        "stations_vector",
        "altimetry_codes",
        "in_situ_unleveled",
        "in_situ_gnss_leveled",
    ]
    rows = [{"item": name, "path": str(p[name]), "exists": p[name].exists()} for name in required]
    report = pd.DataFrame(rows)
    if strict and not report["exists"].all():
        missing = report.loc[~report["exists"], ["item", "path"]].to_dict("records")
        raise FileNotFoundError(f"Missing required inputs: {missing}")
    return report


def normalize_station_id(value) -> str:
    if pd.isna(value):
        return ""
    text = str(value).replace("\ufeff", "").replace("\xa0", " ").strip()
    text = re.sub(r"\s+", "", text)
    if re.fullmatch(r"\d+\.0+", text):
        return text.split(".")[0]
    if re.fullmatch(r"\d+(?:\.\d+)?", text):
        try:
            number = float(text)
            if number.is_integer():
                return str(int(number))
        except Exception:
            pass
    return text


def safe_numeric(values):
    if isinstance(values, pd.Series):
        text = values.astype(str).str.strip().str.replace("%", "", regex=False).str.replace(" ", "", regex=False)
        direct = pd.to_numeric(values, errors="coerce")
        decimal_comma = pd.to_numeric(text.str.replace(",", ".", regex=False), errors="coerce")
        thousand_dot = pd.to_numeric(
            text.str.replace(".", "", regex=False).str.replace(",", ".", regex=False),
            errors="coerce",
        )
        return direct.combine_first(decimal_comma).combine_first(thousand_dot)
    try:
        return float(str(values).replace(",", "."))
    except Exception:
        return np.nan


def read_csv_robust(path: Path | str, dtype=None) -> pd.DataFrame:
    path = Path(path)
    attempts = [
        {"sep": None, "engine": "python", "encoding": "utf-8-sig", "on_bad_lines": "skip"},
        {"sep": ",", "engine": "python", "encoding": "utf-8-sig", "on_bad_lines": "skip"},
        {"sep": ";", "engine": "python", "encoding": "utf-8-sig", "on_bad_lines": "skip"},
        {"sep": "\t", "engine": "python", "encoding": "utf-8-sig", "on_bad_lines": "skip"},
    ]
    best = None
    last_error = None
    for kwargs in attempts:
        try:
            df = pd.read_csv(path, dtype=dtype, **kwargs)
            df.columns = [str(c).replace("\ufeff", "").strip() for c in df.columns]
            if best is None or len(df.columns) > len(best.columns):
                best = df
            if len(df.columns) > 1:
                return df
        except Exception as exc:
            last_error = exc
    if best is not None:
        return best
    raise last_error or ValueError(f"Could not read CSV: {path}")


def parse_datetime_from_candidates(df: pd.DataFrame, candidates: Iterable[str]) -> tuple[pd.Series, str | None]:
    best = pd.Series(pd.NaT, index=df.index)
    best_score = -1
    best_col = None
    cols = list(dict.fromkeys(
        [c for c in candidates if c in df.columns]
        + [c for c in df.columns if any(k in str(c).lower() for k in ["date", "time", "data"])]
    ))
    for col in cols:
        raw = df[col]
        options = [pd.to_datetime(raw, errors="coerce", utc=True)]
        numeric = pd.to_numeric(raw, errors="coerce")
        if numeric.notna().any():
            for unit in ["s", "ms", "us", "ns"]:
                options.append(pd.to_datetime(numeric, unit=unit, errors="coerce", utc=True))
        for parsed in options:
            if getattr(parsed.dt, "tz", None) is not None:
                parsed = parsed.dt.tz_localize(None)
            years = parsed.dropna().dt.year
            realistic = int(((years >= 1990) & (years <= 2100)).sum())
            score = realistic * 100000 + int(parsed.notna().sum())
            if score > best_score:
                best = parsed
                best_score = score
                best_col = col
    return best, best_col


def normalize_hydro_phase(value):
    if pd.isna(value):
        return np.nan
    text = str(value).strip().lower()
    mapping = {
        "low": "Low",
        "seca": "Low",
        "dry": "Low",
        "rising": "Rising",
        "enchente": "Rising",
        "subida": "Rising",
        "high": "High",
        "cheia": "High",
        "flood": "High",
        "falling": "Falling",
        "vazante": "Falling",
        "receding": "Falling",
        "descida": "Falling",
    }
    return mapping.get(text, value if value in HYDRO_PHASE_ORDER else np.nan)


def infer_hydro_phase(wse: pd.Series) -> pd.Series:
    series = safe_numeric(pd.Series(wse)).interpolate(limit_direction="both")
    if len(series) < 4 or series.nunique(dropna=True) < 3:
        return pd.Series(np.nan, index=series.index)
    q25, q75 = series.quantile([0.25, 0.75])
    slope = series.diff().rolling(3, center=True, min_periods=1).mean()
    out = pd.Series("Low", index=series.index, dtype=object)
    out[series >= q75] = "High"
    out[(series > q25) & (series < q75) & (slope >= 0)] = "Rising"
    out[(series > q25) & (series < q75) & (slope < 0)] = "Falling"
    return out


def get_orbital_phase(date, cfg: PipelineConfig):
    dt = pd.to_datetime(date, errors="coerce")
    if pd.isna(dt):
        return np.nan
    return "CalVal" if dt < pd.Timestamp(cfg.calval_cutoff_date) else "Nominal"


def load_metadata(cfg: PipelineConfig) -> pd.DataFrame:
    p = paths(cfg)
    if not p["metadata"].exists():
        return pd.DataFrame()
    raw = read_csv_robust(p["metadata"], dtype=str)
    norm = {c: re.sub(r"[^a-z0-9]+", "_", str(c).lower()).strip("_") for c in raw.columns}
    df = raw.rename(columns=norm).copy()
    station_col = next((c for c in ["codigo", "cod_ana", "codigo_ana", "station", "id"] if c in df.columns), None)
    if station_col is None:
        raise ValueError("Metadata must include codigo/cod_ana/codigo_ana/station/id.")
    out = pd.DataFrame({"station": df[station_col].map(normalize_station_id)})
    aliases = {
        "station_name": ["nome", "name", "station_name"],
        "river": ["rio", "river", "river_name"],
        "latitude": ["latitude", "lat"],
        "longitude": ["longitude", "lon", "long"],
        "width": ["largura", "width"],
        "drainage_area": ["area_drenagem", "drainage_area"],
        "subregion": ["subregiao", "subregion"],
        "pantanal": ["pantanal"],
    }
    for target, choices in aliases.items():
        col = next((c for c in choices if c in df.columns), None)
        out[target] = df[col] if col else np.nan
    for col in ["latitude", "longitude", "width", "drainage_area"]:
        out[col] = safe_numeric(out[col])
    out = out.drop_duplicates("station").query("station != ''").reset_index(drop=True)
    if cfg.station_filter:
        selected = set(map(normalize_station_id, cfg.station_filter))
        out = out[out["station"].isin(selected)].reset_index(drop=True)
    return out


def detect_leveled_stations(cfg: PipelineConfig) -> list[str]:
    p = paths(cfg)
    stations = {
        normalize_station_id(fp.name.replace("_nivelada.csv", "").replace("_leveled.csv", ""))
        for pattern in ["*_nivelada.csv", "*_leveled.csv"]
        for fp in p["in_situ_gnss_leveled"].glob(pattern)
    }
    if cfg.station_filter:
        stations &= set(map(normalize_station_id, cfg.station_filter))
    return sorted(stations)


def load_insitu_series(cfg: PipelineConfig, station: str, leveled: bool = False) -> pd.DataFrame:
    p = paths(cfg)
    station = normalize_station_id(station)
    if leveled:
        candidates = [
            p["in_situ_gnss_leveled"] / f"{station}_leveled.csv",
            p["in_situ_gnss_leveled"] / f"{station}_nivelada.csv",
        ]
    else:
        candidates = [p["in_situ_unleveled"] / f"{station}.csv"]
    file_path = next((candidate for candidate in candidates if candidate.exists()), candidates[0])
    if not file_path.exists():
        return pd.DataFrame()
    df = read_csv_robust(file_path)
    df["data"], _ = parse_datetime_from_candidates(df, ["data", "date", "datetime", "data_ref"])
    wse_col = next((c for c in ["wse_swot_ref", "wse_ana", "wse_egm08", "wse", "WSE", "Cota", "cota", "nivel", "stage"] if c in df.columns), None)
    if wse_col is None:
        raise ValueError(f"{file_path}: WSE column not found.")
    out = pd.DataFrame({"data": df["data"], "wse_insitu": safe_numeric(df[wse_col])})
    phase_col = next((c for c in ["hydro_phase", "phase", "fase", "fase_hidrologica"] if c in df.columns), None)
    out["hydro_phase"] = df[phase_col].apply(normalize_hydro_phase) if phase_col else infer_hydro_phase(out["wse_insitu"])
    out["station"] = station
    out["leveled"] = bool(leveled)
    out = out.dropna(subset=["data", "wse_insitu"])
    out = out[(out["data"] >= pd.Timestamp(cfg.date_start)) & (out["data"] <= pd.Timestamp(cfg.date_end))]
    return out.sort_values("data").reset_index(drop=True)


def split_codes(value) -> list[str]:
    if pd.isna(value):
        return []
    return [c.strip() for c in str(value).split(",") if c.strip() and c.strip() != "-"]


def standardize_altimetry_df(df: pd.DataFrame, source: str, source_code: str | None = None) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    date_col = next((c for c in df.columns if any(k in c.lower() for k in ["date", "time", "data", "datetime"])), None)
    wse_col = next((c for c in df.columns if any(k in c.lower() for k in ["water_level", "wse", "height", "nivel", "level"])), None)
    unc_col = next((c for c in df.columns if any(k in c.lower() for k in ["wse_u", "uncert", "sigma", "std", "error"])), None)
    if date_col is None or wse_col is None:
        raise ValueError(f"Could not detect date/WSE columns for {source}:{source_code}")
    out = pd.DataFrame(
        {
            "date": pd.to_datetime(df[date_col], errors="coerce").dt.normalize(),
            "wse": safe_numeric(df[wse_col]),
            "source_virtual_station": f"{source}:{source_code}" if source_code else source,
        }
    )
    if unc_col:
        out["wse_u"] = safe_numeric(df[unc_col])
    return out.dropna(subset=["date", "wse"]).sort_values("date")


def download_dahiti_station(dahiti_id: str, out_csv: Path) -> Path:
    import requests

    api_key = os.getenv("DAHITI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("Set DAHITI_API_KEY to download DAHITI data.")
    url = "https://dahiti.dgfi.tum.de/api/v2/download-water-level/"
    payload = {"api_key": api_key, "dahiti_id": int(dahiti_id), "format": "csv"}
    response = requests.post(url, json=payload, timeout=60)
    if response.status_code != 200:
        response = requests.get(url, params=payload, timeout=60)
    response.raise_for_status()
    if response.text.lstrip().startswith("<"):
        raise RuntimeError(f"Unexpected HTML response for DAHITI {dahiti_id}")
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    out_csv.write_text(response.text, encoding="utf-8")
    return out_csv


def read_hydroweb_txt(path: Path, code: str) -> pd.DataFrame:
    df = pd.read_csv(
        path,
        sep=r"\s+",
        comment="#",
        header=None,
        usecols=[0, 2, 3],
        names=["date", "wse", "wse_u"],
        engine="python",
    )
    return standardize_altimetry_df(df, "HYDROWEB", code)


def filename_matches_code(filename: str, code: str) -> bool:
    return bool(re.search(rf"(?<![A-Za-z0-9]){re.escape(str(code))}(?![A-Za-z0-9])", str(filename)))


def download_hydroweb_zip(cfg: PipelineConfig, out_zip: Path) -> Path:
    api_key = os.getenv("HYDROWEB_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("Set HYDROWEB_API_KEY to download HydroWeb data.")
    try:
        from py_hydroweb import Client, DownloadBasket
    except Exception as exc:
        raise ImportError("Install py-hydroweb or place HydroWeb TXT files manually.") from exc
    out_zip.parent.mkdir(parents=True, exist_ok=True)
    client = Client(hydroweb_api_url="https://hydroweb.next.theia-land.fr/api", api_key=api_key)
    basket = DownloadBasket("Pantanal_WSE_Basket")
    basket.add_collection("HYDROWEB_RIVERS_OPE", bbox=list(cfg.hydroweb_bbox))
    basket.add_collection("HYDROWEB_RIVERS_RESEARCH", bbox=list(cfg.hydroweb_bbox))
    client.submit_and_download_zip(basket, zip_filename=out_zip.name, output_folder=out_zip.parent)
    if not out_zip.exists():
        raise FileNotFoundError(f"HydroWeb ZIP was not created: {out_zip}")
    return out_zip


def extract_hydroweb_code_from_zip(cfg: PipelineConfig, code: str, target_txt: Path, zip_path: Path | None = None) -> Path:
    target_txt.parent.mkdir(parents=True, exist_ok=True)
    zip_path = zip_path or Path(cfg.project_root).resolve() / "outputs" / "hydroweb_download" / "hydroweb_pantanal.zip"
    if not zip_path.exists():
        download_hydroweb_zip(cfg, zip_path)
    with zipfile.ZipFile(zip_path, "r") as zf:
        candidates = [name for name in zf.namelist() if name.lower().endswith(".txt") and filename_matches_code(Path(name).name, code)]
        if not candidates:
            raise FileNotFoundError(f"HydroWeb code {code} not found in {zip_path}")
        with zf.open(candidates[0]) as src, target_txt.open("wb") as dst:
            shutil.copyfileobj(src, dst)
    return target_txt


def consolidate_altimetry(cfg: PipelineConfig, data_cut: str = "2023-01-01") -> pd.DataFrame:
    p = paths(cfg)
    if not p["altimetry_codes"].exists():
        return pd.DataFrame()
    mapping = read_csv_robust(p["altimetry_codes"], dtype=str)
    if "cod_ana" not in mapping.columns:
        raise ValueError("The altimetry station-code table must include cod_ana.")
    summary = []
    for _, row in mapping.iterrows():
        station = normalize_station_id(row.get("cod_ana"))
        station_path = station_dir(cfg, cfg.altimetry_station_dir_template, station)
        series = []
        for code in split_codes(row.get("cod_dahiti")):
            raw_csv = station_path / "dahiti" / f"{code}.csv"
            if cfg.run_altimetry_downloads and (cfg.overwrite_outputs or not raw_csv.exists()):
                download_dahiti_station(code, raw_csv)
            if raw_csv.exists():
                series.append(standardize_altimetry_df(read_csv_robust(raw_csv), "DAHITI", code))
        for code in split_codes(row.get("cod_hidroweb")):
            raw_txt = station_path / "hydroweb" / f"{code}.txt"
            raw_csv = station_path / "hydroweb" / f"{code}.csv"
            if cfg.run_altimetry_downloads and (cfg.overwrite_outputs or not raw_txt.exists()):
                try:
                    extract_hydroweb_code_from_zip(cfg, code, raw_txt)
                except Exception as exc:
                    print(f"HydroWeb download {station}/{code}: {exc}")
            if raw_csv.exists():
                series.append(standardize_altimetry_df(read_csv_robust(raw_csv), "HYDROWEB", code))
            elif raw_txt.exists():
                series.append(read_hydroweb_txt(raw_txt, code))
        if not series:
            summary.append({"station": station, "selected_source": None, "n_obs": 0})
            continue
        combined = pd.concat(series, ignore_index=True)
        combined = combined[combined["date"] >= pd.Timestamp(data_cut)].copy()
        if combined.empty:
            summary.append({"station": station, "selected_source": None, "n_obs": 0})
            continue
        combined["source_name"] = combined["source_virtual_station"].str.split(":").str[0]
        selected_source = combined.groupby("source_name").size().sort_values(ascending=False).index[0]
        selected = combined[combined["source_name"] == selected_source].copy()
        agg = {"wse": "mean", "source_virtual_station": lambda x: " | ".join(sorted(set(map(str, x))))}
        if "wse_u" in selected.columns:
            agg["wse_u"] = "mean"
        final = selected.groupby("date", as_index=False).agg(agg).sort_values("date")
        final["source_selected"] = selected_source
        out_csv = station_path / f"alt_conv_{station}.csv"
        out_csv.parent.mkdir(parents=True, exist_ok=True)
        final.to_csv(out_csv, index=False)
        summary.append({"station": station, "selected_source": selected_source, "n_obs": len(final), "output": str(out_csv)})
    out = pd.DataFrame(summary)
    out.to_csv(p["tables"] / "altimetry_consolidation_summary.csv", index=False)
    return out


def calc_metrics(y_true, y_pred, include_bias: bool = True) -> dict:
    y1 = safe_numeric(pd.Series(y_true))
    y2 = safe_numeric(pd.Series(y_pred))
    mask = ~(y1.isna() | y2.isna())
    y1 = y1[mask].to_numpy(dtype=float)
    y2 = y2[mask].to_numpy(dtype=float)
    out = {"mae": np.nan, "rmse": np.nan, "spearman_r": np.nan, "spearman_p": np.nan, "n_obs": int(len(y1))}
    if include_bias:
        out["bias"] = np.nan
    if len(y1) < 2:
        return out
    out["mae"] = float(np.mean(np.abs(y2 - y1)))
    out["rmse"] = float(np.sqrt(np.mean((y2 - y1) ** 2)))
    rho, p_value = stats.spearmanr(y1, y2)
    out["spearman_r"] = float(rho) if pd.notna(rho) else np.nan
    out["spearman_p"] = float(p_value) if pd.notna(p_value) else np.nan
    if include_bias:
        out["bias"] = float(np.mean(y2 - y1))
    return out


def rolling_hampel_flags(values, window_size=5, n_sigma=3.0, min_periods=3, mad_scale=1.4826):
    series = pd.Series(values, dtype="float64")
    median = series.rolling(window_size, center=True, min_periods=min_periods).median()
    mad = (series - median).abs().rolling(window_size, center=True, min_periods=min_periods).median()
    threshold = n_sigma * mad_scale * mad
    deviation = (series - median).abs()
    flags = ((threshold > 0) & (deviation > threshold)).fillna(False)
    return flags.to_numpy(), median.to_numpy(), mad.to_numpy(), threshold.to_numpy(), deviation.to_numpy()


def apply_hampel_filter(df: pd.DataFrame, value_col="wse_sat", date_col="data", group_cols=("station", "product")):
    if df.empty or value_col not in df.columns:
        return df.copy(), df.copy()
    filtered_parts = []
    audit_parts = []
    by = [c for c in group_cols if c in df.columns]
    groups = df.groupby(by) if by else [(None, df)]
    for _, group in groups:
        work = group.sort_values(date_col).copy()
        work[value_col] = safe_numeric(work[value_col])
        flags, median, mad, threshold, deviation = rolling_hampel_flags(work[value_col])
        work["hampel_median"] = median
        work["hampel_mad"] = mad
        work["hampel_threshold"] = threshold
        work["hampel_abs_deviation"] = deviation
        work["is_hampel_outlier"] = flags
        work["is_outlier_any"] = flags
        audit_parts.append(work)
        filtered_parts.append(work.loc[~work["is_outlier_any"]].copy())
    filtered = pd.concat(filtered_parts, ignore_index=True) if filtered_parts else pd.DataFrame()
    audit = pd.concat(audit_parts, ignore_index=True) if audit_parts else pd.DataFrame()
    return filtered, audit


def nearest_match_no_reuse(df_ref: pd.DataFrame, df_sat: pd.DataFrame, window_days: int) -> pd.DataFrame:
    if df_ref.empty or df_sat.empty:
        return pd.DataFrame()
    ref = df_ref.dropna(subset=["data"]).sort_values("data").reset_index(drop=True).copy()
    sat = df_sat.dropna(subset=["data"]).sort_values("data").reset_index(drop=True).copy()
    if ref.empty or sat.empty:
        return pd.DataFrame()
    sat_times = sat["data"].astype("int64").to_numpy()
    ref_times = ref["data"].astype("int64").to_numpy()
    window_ns = pd.Timedelta(days=window_days).value
    used = np.zeros(len(sat), dtype=bool)
    rows = []
    for i, ref_time in enumerate(ref_times):
        lo = np.searchsorted(sat_times, ref_time - window_ns, side="left")
        hi = np.searchsorted(sat_times, ref_time + window_ns, side="right")
        candidates = np.flatnonzero(~used[lo:hi]) + lo
        if candidates.size == 0:
            continue
        best_idx = candidates[np.abs(sat_times[candidates] - ref_time).argmin()]
        used[best_idx] = True
        best = sat.loc[best_idx]
        row = {
            "date_ref": ref.loc[i, "data"],
            "date_sat": best["data"],
            "wse_insitu": ref.loc[i, "wse_insitu"],
            "wse_sat": best["wse_sat"],
            "hydro_phase": ref.loc[i, "hydro_phase"] if "hydro_phase" in ref.columns else np.nan,
            "orbital_phase": best.get("orbital_phase", np.nan),
        }
        for col in sat.columns:
            if col not in {"data", "wse_sat", "orbital_phase"}:
                row[col] = best[col]
        rows.append(row)
    return pd.DataFrame(rows)


SWOT_SCHEMAS = {
    "pixc": {"file": "pixc_complete_raw.csv", "date_cols": ["data", "arquivo"], "wse_cols": ["wse_media", "wse", "height_media"]},
    "raster": {"file": "raster_complete_raw.csv", "date_cols": ["data", "arquivo"], "wse_cols": ["wse_media", "wse", "height"]},
    "node": {"file": "node_complete_raw.csv", "date_cols": ["data", "time_str", "timestamp_arquivo", "arquivo_origem"], "wse_cols": ["wse", "WSE", "wse_sm"]},
    "reach": {"file": "reach_complete_raw.csv", "date_cols": ["data", "time_str", "timestamp_arquivo", "arquivo_origem"], "wse_cols": ["wse", "WSE"]},
}


def find_product_file(cfg: PipelineConfig, station: str, product: str) -> Path | None:
    base = station_dir(cfg, cfg.swot_station_dir_template, station)
    direct = base / product / SWOT_SCHEMAS[product]["file"]
    if direct.exists():
        return direct
    flat = base / SWOT_SCHEMAS[product]["file"]
    return flat if flat.exists() else None


def load_swot_product(cfg: PipelineConfig, station: str, product: str) -> pd.DataFrame:
    file_path = find_product_file(cfg, station, product)
    if file_path is None:
        return pd.DataFrame()
    df = read_csv_robust(file_path)
    schema = SWOT_SCHEMAS[product]
    df["data"], date_source = parse_datetime_from_candidates(df, schema["date_cols"])
    wse_col = next((c for c in schema["wse_cols"] if c in df.columns), None)
    if wse_col is None:
        return pd.DataFrame()
    out = df.copy()
    out["station"] = station
    out["product"] = product
    out["wse_sat"] = safe_numeric(df[wse_col])
    out["orbital_phase"] = out["data"].apply(lambda x: get_orbital_phase(x, cfg))
    version_source = pd.Series("", index=out.index, dtype=object)
    for candidate_col in ["arquivo", "arquivo_origem", "filename", "granule"]:
        if candidate_col in out.columns:
            version_source = version_source.where(version_source.astype(str).str.len() > 0, out[candidate_col].astype(str))
    out["swot_version"] = version_source.astype(str).str.extract(r"_(C|D|2\.0|PIC0|PGC0)_", expand=False)
    out["time_source_column"] = date_source
    out["wse_source_column"] = wse_col
    out = out.dropna(subset=["data", "wse_sat"])
    out = out[(out["data"] >= pd.Timestamp(cfg.date_start)) & (out["data"] <= pd.Timestamp(cfg.date_end))]
    out = out[out["wse_sat"] > -1e9]
    return out.sort_values("data").reset_index(drop=True)


def load_altimetry_product(cfg: PipelineConfig, station: str) -> pd.DataFrame:
    base = station_dir(cfg, cfg.altimetry_station_dir_template, station)
    files = list(base.glob("alt_conv_*.csv"))
    if not files:
        return pd.DataFrame()
    parts = []
    for file_path in files:
        df = read_csv_robust(file_path)
        df["data"], _ = parse_datetime_from_candidates(df, ["date", "data"])
        wse_col = next((c for c in ["wse", "WSE", "water_level", "height"] if c in df.columns), None)
        if wse_col:
            parts.append(pd.DataFrame({"data": df["data"], "wse_sat": safe_numeric(df[wse_col])}))
    if not parts:
        return pd.DataFrame()
    out = pd.concat(parts, ignore_index=True).dropna(subset=["data", "wse_sat"])
    out["data"] = out["data"].dt.normalize()
    out = out.groupby("data", as_index=False)["wse_sat"].mean()
    out["station"] = station
    out["product"] = "altimetry"
    out["orbital_phase"] = out["data"].apply(lambda x: get_orbital_phase(x, cfg))
    return out.sort_values("data").reset_index(drop=True)


def quality_filter_product(df: pd.DataFrame, product: str) -> pd.DataFrame:
    if df.empty:
        return df
    out = df.copy()
    if "swot_version" in out.columns and product in PRODUCTS_SWOT:
        out = out[~out["swot_version"].astype(str).str.contains("PIC0|PGC0", na=False)]
    if product == "node" and "node_q" in out.columns:
        out = out[safe_numeric(out["node_q"]) < 2]
    if product == "reach" and "reach_q" in out.columns:
        out = out[safe_numeric(out["reach_q"]) < 2]
    if product == "raster" and "wse_qual_media" in out.columns:
        out = out[safe_numeric(out["wse_qual_media"]) < 1.8]
    return out


def build_matchups(cfg: PipelineConfig, metadata: pd.DataFrame, leveled_stations: list[str]):
    stage_rows = {"raw": [], "quality_filtered": [], "outlier_filtered": []}
    audits = []
    if metadata.empty:
        return {key: pd.DataFrame() for key in stage_rows}, pd.DataFrame()
    for _, station_meta in metadata.iterrows():
        station = station_meta["station"]
        is_leveled = station in leveled_stations
        insitu = load_insitu_series(cfg, station, leveled=is_leveled)
        if insitu.empty:
            insitu = load_insitu_series(cfg, station, leveled=False)
        if insitu.empty:
            continue
        for product in PRODUCTS_ALL:
            sat = load_altimetry_product(cfg, station) if product == "altimetry" else load_swot_product(cfg, station, product)
            if sat.empty:
                continue
            raw = sat.copy()
            quality = quality_filter_product(raw, product)
            filtered, audit = apply_hampel_filter(quality)
            if not audit.empty:
                audits.append(audit.assign(stage="hampel", station=station, product=product))
            for stage, table in [("raw", raw), ("quality_filtered", quality), ("outlier_filtered", filtered)]:
                matchups = nearest_match_no_reuse(insitu, table, cfg.match_window_days)
                if matchups.empty:
                    continue
                for col in ["station_name", "river", "latitude", "longitude", "width", "drainage_area", "subregion", "pantanal"]:
                    matchups[col] = station_meta.get(col, np.nan)
                matchups["station"] = station
                matchups["product"] = product
                matchups["station_group"] = "leveled" if is_leveled else "nonleveled"
                matchups["lineage_stage"] = stage
                matchups["signed_error"] = safe_numeric(matchups["wse_sat"]) - safe_numeric(matchups["wse_insitu"])
                matchups["abs_error"] = matchups["signed_error"].abs()
                stage_rows[stage].append(matchups)
    matchups_by_stage = {key: pd.concat(value, ignore_index=True) if value else pd.DataFrame() for key, value in stage_rows.items()}
    audit_df = pd.concat(audits, ignore_index=True) if audits else pd.DataFrame()
    return matchups_by_stage, audit_df


def aggregate_metrics(df: pd.DataFrame, keys: list[str], ref_col="wse_insitu", sat_col="wse_sat") -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    rows = []
    for values, group in df.groupby(keys):
        values = values if isinstance(values, tuple) else (values,)
        rec = dict(zip(keys, values))
        rec.update(calc_metrics(group[ref_col], group[sat_col], include_bias=True))
        rec["n_stations"] = int(group["station"].nunique()) if "station" in group.columns else np.nan
        rows.append(rec)
    return pd.DataFrame(rows)


def build_dynamic_metrics(df: pd.DataFrame):
    rows = []
    examples = []
    if df.empty:
        return pd.DataFrame(), pd.DataFrame()
    for (station, product), group in df.groupby(["station", "product"]):
        group = group.sort_values("date_ref").copy()
        if len(group) < 5:
            continue
        ref = safe_numeric(group["wse_insitu"])
        sat = safe_numeric(group["wse_sat"])
        valid = ~(ref.isna() | sat.isna())
        group = group.loc[valid].copy()
        if len(group) < 5:
            continue
        if group["wse_insitu"].max() == group["wse_insitu"].min() or group["wse_sat"].max() == group["wse_sat"].min():
            continue
        group["insitu_norm"] = (group["wse_insitu"] - group["wse_insitu"].min()) / (group["wse_insitu"].max() - group["wse_insitu"].min())
        group["sat_norm"] = (group["wse_sat"] - group["wse_sat"].min()) / (group["wse_sat"].max() - group["wse_sat"].min())
        met = calc_metrics(group["insitu_norm"], group["sat_norm"], include_bias=False)
        rows.append(
            {
                "station": station,
                "product": product,
                "station_group": group["station_group"].iloc[0],
                "n_obs": met["n_obs"],
                "spearman_r": met["spearman_r"],
                "spearman_p": met["spearman_p"],
            }
        )
        examples.append(group[["station", "product", "date_ref", "insitu_norm", "sat_norm", "station_group", "hydro_phase"]].copy())
    return pd.DataFrame(rows), pd.concat(examples, ignore_index=True) if examples else pd.DataFrame()


def save_table(df: pd.DataFrame, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)


def run_analysis(cfg: PipelineConfig) -> dict[str, pd.DataFrame]:
    p = paths(cfg)
    metadata = load_metadata(cfg)
    leveled = detect_leveled_stations(cfg)
    matchups, outlier_audit = build_matchups(cfg, metadata, leveled)
    for stage, df in matchups.items():
        save_table(df, p["tables"] / f"matchups_{stage}.csv")
    save_table(outlier_audit, p["tables"] / "outlier_filter_audit.csv")

    all_outlier = matchups.get("outlier_filtered", pd.DataFrame())
    absolute = all_outlier[all_outlier.get("station_group", pd.Series(dtype=str)).eq("leveled")].copy() if not all_outlier.empty else pd.DataFrame()
    metrics_overall = aggregate_metrics(absolute, ["product"])
    metrics_station = aggregate_metrics(absolute, ["station", "product"])
    metrics_orbital = aggregate_metrics(absolute, ["product", "orbital_phase"]) if not absolute.empty else pd.DataFrame()
    metrics_phase = aggregate_metrics(absolute[absolute["product"].isin(PRODUCTS_SWOT)] if not absolute.empty else absolute, ["product", "hydro_phase"])
    metrics_dynamic_station, normalized_examples = build_dynamic_metrics(all_outlier)
    metrics_dynamic_overall = (
        metrics_dynamic_station.groupby("product", as_index=False).agg(
            n_station_series=("station", "size"),
            n_obs=("n_obs", "sum"),
            median_spearman=("spearman_r", "median"),
            mean_spearman=("spearman_r", "mean"),
        )
        if not metrics_dynamic_station.empty
        else pd.DataFrame()
    )

    tables = {
        "metadata": metadata,
        "matchups_raw": matchups.get("raw", pd.DataFrame()),
        "matchups_quality_filtered": matchups.get("quality_filtered", pd.DataFrame()),
        "matchups_outlier_filtered": all_outlier,
        "outlier_filter_audit": outlier_audit,
        "metrics_absolute_overall": metrics_overall,
        "metrics_absolute_by_station": metrics_station,
        "metrics_absolute_by_orbital_phase": metrics_orbital,
        "metrics_absolute_by_hydro_phase": metrics_phase,
        "metrics_dynamic_by_station": metrics_dynamic_station,
        "metrics_dynamic_overall": metrics_dynamic_overall,
        "normalized_series_for_examples": normalized_examples,
    }

    output_names = {
        "metrics_absolute_overall": ["metrics_absolute_overall.csv", "metrics_overall.csv"],
        "metrics_absolute_by_station": ["metrics_absolute_by_station.csv", "metrics_by_station.csv"],
        "metrics_absolute_by_orbital_phase": ["metrics_absolute_by_orbital_phase.csv", "metrics_by_product_orbital_phase.csv"],
        "metrics_absolute_by_hydro_phase": ["metrics_absolute_by_hydro_phase.csv", "error_by_hydrological_phase.csv"],
        "metrics_dynamic_by_station": ["metrics_dynamic_by_station.csv"],
        "metrics_dynamic_overall": ["metrics_dynamic_overall.csv"],
        "normalized_series_for_examples": ["normalized_series_for_examples.csv"],
    }
    for key, filenames in output_names.items():
        for filename in filenames:
            save_table(tables[key], p["tables"] / filename)

    summary = execution_summary(cfg, tables, leveled)
    (p["tables"] / "execution_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    tables["execution_summary"] = pd.DataFrame([summary])
    return tables


def execution_summary(cfg: PipelineConfig, tables: dict[str, pd.DataFrame], leveled_stations: list[str]) -> dict:
    p = paths(cfg)
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "project_root": str(p["root"]),
        "date_start": cfg.date_start,
        "date_end": cfg.date_end,
        "match_window_days": cfg.match_window_days,
        "n_metadata_stations": int(len(tables.get("metadata", pd.DataFrame()))),
        "n_leveled_stations": int(len(leveled_stations)),
        "n_matchups_raw": int(len(tables.get("matchups_raw", pd.DataFrame()))),
        "n_matchups_quality_filtered": int(len(tables.get("matchups_quality_filtered", pd.DataFrame()))),
        "n_matchups_outlier_filtered": int(len(tables.get("matchups_outlier_filtered", pd.DataFrame()))),
        "n_absolute_matchups": int(len(tables.get("metrics_absolute_by_station", pd.DataFrame()))),
        "n_dynamic_station_product_series": int(len(tables.get("metrics_dynamic_by_station", pd.DataFrame()))),
        "tables_dir": str(p["tables"]),
        "figures_dir": str(p["figures"]),
    }


def savefig(cfg: PipelineConfig, fig, name: str) -> Path:
    out = paths(cfg)["figures"] / f"{name}.png"
    fig.savefig(out, bbox_inches="tight", dpi=300)
    plt.close(fig)
    return out


def plot_absolute_product_metrics(cfg: PipelineConfig, metrics: pd.DataFrame) -> Path | None:
    if metrics.empty:
        return None
    fig, axes = plt.subplots(1, 3, figsize=(13, 4))
    for ax, metric, label in zip(axes, ["mae", "rmse", "bias"], ["MAE (m)", "RMSE (m)", "Bias (m)"]):
        data = metrics.sort_values(metric)
        ax.bar(data["product"].map(PRODUCT_LABELS), data[metric], color=[PRODUCT_COLORS.get(p, "#888") for p in data["product"]])
        ax.axhline(0, color="#333", lw=0.8)
        ax.set_ylabel(label)
        ax.grid(axis="y", alpha=0.25)
    fig.suptitle("Absolute performance by product")
    fig.tight_layout()
    return savefig(cfg, fig, "fig_absolute_product_metrics")


def plot_dynamic_summary(cfg: PipelineConfig, metrics: pd.DataFrame) -> Path | None:
    if metrics.empty:
        return None
    fig, ax = plt.subplots(figsize=(7, 4))
    data = metrics.sort_values("median_spearman", ascending=False)
    ax.bar(data["product"].map(PRODUCT_LABELS), data["median_spearman"], color=[PRODUCT_COLORS.get(p, "#888") for p in data["product"]])
    ax.set_ylim(-1, 1)
    ax.axhline(0, color="#333", lw=0.8)
    ax.set_ylabel("Median Spearman")
    ax.set_title("Normalized dynamic validation")
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    return savefig(cfg, fig, "fig_dynamic_spearman_summary")


def plot_station_diagnostic(cfg: PipelineConfig, matchups: pd.DataFrame, station: str | None = None, product: str | None = None) -> Path | None:
    if matchups.empty:
        return None
    work = matchups.copy()
    station = station or work.groupby("station").size().sort_values(ascending=False).index[0]
    product = product or work[work["station"] == station].groupby("product").size().sort_values(ascending=False).index[0]
    group = work[(work["station"] == station) & (work["product"] == product)].sort_values("date_ref")
    if group.empty:
        return None
    met = calc_metrics(group["wse_insitu"], group["wse_sat"], include_bias=True)
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5))
    axes[0].plot(group["date_ref"], group["wse_insitu"], "-o", ms=3, label="In situ", color="#1f77b4")
    axes[0].plot(group["date_sat"], group["wse_sat"], "-o", ms=3, label=PRODUCT_LABELS.get(product, product), color=PRODUCT_COLORS.get(product, "#888"))
    axes[0].set_ylabel("WSE (m)")
    axes[0].legend(frameon=False)
    axes[0].grid(alpha=0.25)
    axes[1].scatter(group["wse_insitu"], group["wse_sat"], color=PRODUCT_COLORS.get(product, "#888"), alpha=0.8)
    lo = np.nanmin([group["wse_insitu"].min(), group["wse_sat"].min()])
    hi = np.nanmax([group["wse_insitu"].max(), group["wse_sat"].max()])
    axes[1].plot([lo, hi], [lo, hi], "--", color="#333", lw=1)
    axes[1].set_xlabel("In situ WSE (m)")
    axes[1].set_ylabel("Satellite/altimetry WSE (m)")
    axes[1].set_title(f"MAE={met['mae']:.2f} m | RMSE={met['rmse']:.2f} m | rho={met['spearman_r']:.2f}")
    axes[1].grid(alpha=0.25)
    fig.suptitle(f"Station {station} - {PRODUCT_LABELS.get(product, product)}")
    fig.tight_layout()
    return savefig(cfg, fig, f"fig_station_diagnostic_{station}_{product}")


def plot_outlier_audit(cfg: PipelineConfig, audit: pd.DataFrame) -> Path | None:
    if audit.empty or "is_outlier_any" not in audit.columns:
        return None
    data = audit.groupby("product", as_index=False).agg(n_total=("is_outlier_any", "size"), n_removed=("is_outlier_any", "sum"))
    data["removed_pct"] = 100 * data["n_removed"] / data["n_total"].replace(0, np.nan)
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.bar(data["product"].map(PRODUCT_LABELS), data["removed_pct"], color=[PRODUCT_COLORS.get(p, "#888") for p in data["product"]])
    ax.set_ylabel("Outliers removed (%)")
    ax.set_title("Hampel filter audit")
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    return savefig(cfg, fig, "fig_hampel_outlier_audit")


def generate_figures(cfg: PipelineConfig, tables: dict[str, pd.DataFrame]) -> pd.DataFrame:
    figure_paths = [
        plot_absolute_product_metrics(cfg, tables.get("metrics_absolute_overall", pd.DataFrame())),
        plot_dynamic_summary(cfg, tables.get("metrics_dynamic_overall", pd.DataFrame())),
        plot_station_diagnostic(cfg, tables.get("matchups_outlier_filtered", pd.DataFrame())),
        plot_outlier_audit(cfg, tables.get("outlier_filter_audit", pd.DataFrame())),
    ]
    manifest = pd.DataFrame({"figure_path": [str(p) for p in figure_paths if p]})
    manifest.to_csv(paths(cfg)["tables"] / "figure_manifest.csv", index=False)
    return manifest


SWOT_SHORT_NAMES = {
    "pixc": ["SWOT_L2_HR_PIXC_D", "SWOT_L2_HR_PIXC_2.0"],
    "raster": ["SWOT_L2_HR_Raster_D", "SWOT_L2_HR_Raster_2.0"],
    "node": ["SWOT_L2_HR_RiverSP_D", "SWOT_L2_HR_RiverSP_2.0"],
    "reach": ["SWOT_L2_HR_RiverSP_D", "SWOT_L2_HR_RiverSP_2.0"],
}


def run_swot_acquisition(cfg: PipelineConfig) -> pd.DataFrame:
    raise NotImplementedError(
        "SWOT acquisition is not enabled in this compact final workflow. "
        "Populate the configured SWOT station folders before running the final analysis."
    )


def run_pipeline(cfg: PipelineConfig, make_figures: bool = True) -> dict[str, pd.DataFrame]:
    if cfg.run_altimetry_downloads:
        consolidate_altimetry(cfg)
    if cfg.run_swot_downloads:
        run_swot_acquisition(cfg)
    tables = run_analysis(cfg)
    if make_figures:
        tables["figure_manifest"] = generate_figures(cfg, tables)
    return tables
