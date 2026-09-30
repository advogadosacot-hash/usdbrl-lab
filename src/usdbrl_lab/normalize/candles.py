"""Candles canônicos de ``market_data`` (seção 20).

Regras (seção 5): timestamps em UTC rotulados pelo início; candle só entra quando fechado
(agora >= início + intervalo + tolerância); ``is_valid`` indica valores reais da fonte.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd

from usdbrl_lab.common.clock import ensure_utc
from usdbrl_lab.sources.yahoo import INTERVAL_SECONDS, OHLC

MARKET_DATA_COLUMNS = [
    "symbol",
    "interval",
    "event_time",
    *OHLC,
    "is_valid",
    "is_imputed",
    "is_incomplete",
    "quality_flag",
    "source",
    "source_mode",
    "is_backfill",
    "available_time",
    "ingested_at",
    "run_id",
]


def canonical_candles(
    raw: pd.DataFrame,
    *,
    symbol: str,
    interval: str,
    source: str,
    run_id: str,
    now: datetime,
    ingested_at: datetime,
    backfill: bool,
    close_grace_minutes: int,
    source_mode: str = "normal",
) -> tuple[pd.DataFrame, int]:
    """Devolve (candles fechados, quantos foram descartados por ainda estarem abertos)."""
    now, ingested_at = ensure_utc(now), ensure_utc(ingested_at)
    step = pd.Timedelta(seconds=INTERVAL_SECONDS[interval])
    grace = pd.Timedelta(minutes=close_grace_minutes)
    frame = raw.copy()
    if frame.empty:
        return pd.DataFrame(columns=MARKET_DATA_COLUMNS), 0
    closed = frame["event_time"] + step + grace <= pd.Timestamp(now)
    n_open = int((~closed).sum())
    frame = frame.loc[closed].reset_index(drop=True)
    frame["symbol"] = symbol
    frame["interval"] = interval
    frame["is_valid"] = frame[OHLC].notna().all(axis=1)
    frame["is_imputed"] = False
    frame["is_incomplete"] = False
    frame["quality_flag"] = pd.Series([""] * len(frame), dtype="string")
    frame["source"] = source
    frame["source_mode"] = source_mode
    frame["is_backfill"] = backfill
    # Backfill: disponível no fim do candle + tolerância. Ao vivo: instante da coleta.
    end_plus_grace = frame["event_time"] + step + grace
    if backfill:
        frame["available_time"] = end_plus_grace
    else:
        frame["available_time"] = end_plus_grace.clip(lower=pd.Timestamp(ingested_at))
    frame["ingested_at"] = pd.Timestamp(ingested_at)
    frame["run_id"] = run_id
    return frame[MARKET_DATA_COLUMNS], n_open


def interval_timedelta(interval: str) -> timedelta:
    return timedelta(seconds=INTERVAL_SECONDS[interval])
