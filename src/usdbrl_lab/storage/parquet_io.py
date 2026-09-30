"""Leitura, merge e escrita de partições diárias (UTC) em Parquet.

Merge idempotente: se o candle já existe com os mesmos valores da fonte, a linha antiga é
mantida (sem reescrever o arquivo). Se a fonte revisou o valor, entram os valores novos e
``available_time`` fica o menor dos dois. Um arquivo só é regravado quando muda.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from usdbrl_lab.storage.layout import market_data_dir, market_data_file

OHLC = ["open", "high", "low", "close"]
TIME_COLUMNS = ("event_time", "available_time", "ingested_at")
TIME_DTYPE = "datetime64[us, UTC]"


def normalize_times(frame: pd.DataFrame) -> pd.DataFrame:
    """Uma única resolução para todas as colunas de tempo (evita diferenças entre execuções)."""
    for col in TIME_COLUMNS:
        if col in frame:
            frame[col] = frame[col].astype(TIME_DTYPE)
    return frame


def _raw_values(frame: pd.DataFrame, value_cols: list[str]) -> pd.DataFrame:
    """Valores como vieram da fonte (candles imputados voltam a ser ausentes)."""
    vals = frame[value_cols].copy()
    if "is_imputed" in frame:
        vals.loc[frame["is_imputed"].fillna(False).astype(bool)] = np.nan
    return vals


def read_days(
    root: Path, symbol: str, interval: str, start: date | None = None, end: date | None = None
) -> pd.DataFrame:
    base = market_data_dir(root, symbol, interval)
    if not base.exists():
        return pd.DataFrame()
    frames = []
    for path in sorted(base.glob("*/*/*.parquet")):
        day = date(int(path.parent.parent.name), int(path.parent.name), int(path.stem))
        if (start and day < start) or (end and day > end):
            continue
        frames.append(pd.read_parquet(path))
    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames, ignore_index=True).sort_values("event_time", ignore_index=True)
    return normalize_times(out)


def last_event_time(root: Path, symbol: str, interval: str) -> pd.Timestamp | None:
    base = market_data_dir(root, symbol, interval)
    files = sorted(base.glob("*/*/*.parquet")) if base.exists() else []
    if not files:
        return None
    return pd.read_parquet(files[-1], columns=["event_time"])["event_time"].max()


def merge_rows(
    existing: pd.DataFrame,
    new: pd.DataFrame,
    key: str = "event_time",
    value_cols: list[str] | None = None,
) -> tuple[pd.DataFrame, int]:
    """Devolve (merge, número de revisões de valor pela fonte)."""
    value_cols = value_cols or OHLC
    existing, new = normalize_times(existing.copy()), normalize_times(new.copy())
    if existing.empty:
        return new.sort_values(key, ignore_index=True), 0
    if new.empty:
        return existing.sort_values(key, ignore_index=True), 0
    old = existing.set_index(key)
    fresh = new.set_index(key)
    common = old.index.intersection(fresh.index)
    replace = []
    if len(common):
        a = _raw_values(old.loc[common], value_cols).reset_index(drop=True)
        b = _raw_values(fresh.loc[common], value_cols).reset_index(drop=True)
        same = ((a == b) | (a.isna() & b.isna())).all(axis=1).to_numpy()
        replace = list(common[~same])
    revised = len(replace)
    if replace:
        earliest = np.minimum(
            old.loc[replace, "available_time"], fresh.loc[replace, "available_time"]
        )
        old.loc[replace] = fresh.loc[replace]
        old.loc[replace, "available_time"] = earliest
    added = fresh.loc[fresh.index.difference(old.index)]
    merged = pd.concat([old, added]).reset_index().sort_values(key, ignore_index=True)
    return merged, revised


def write_days(root: Path, symbol: str, interval: str, frame: pd.DataFrame) -> list[Path]:
    """Grava uma partição por dia UTC; só regrava arquivos cujo conteúdo mudou."""
    written: list[Path] = []
    if frame.empty:
        return written
    frame = normalize_times(frame.copy())
    for day, part in frame.groupby(frame["event_time"].dt.date):
        path = market_data_file(root, symbol, interval, day)
        part = part.sort_values("event_time", ignore_index=True)
        if path.exists():
            current = normalize_times(pd.read_parquet(path))
            if current.shape == part.shape and current.equals(part[current.columns]):
                continue
        path.parent.mkdir(parents=True, exist_ok=True)
        part.to_parquet(path, index=False, compression="zstd")
        written.append(path)
    return written
