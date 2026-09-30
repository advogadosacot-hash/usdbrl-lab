"""Regras por candle da seção 6, aplicadas de forma idempotente.

A cada execução as marcas são recalculadas a partir dos valores originais da fonte:
candles imputados voltam a ser "ausentes" antes de reaplicar as regras.

Sem segunda fonte intraday na V1 (AwesomeAPI bloqueada, P6), uma mudança anormal não
pode ser confirmada e, pela regra da seção 6, é rejeitada.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import numpy as np
import pandas as pd

OHLC = ["open", "high", "low", "close"]

FLAG_IMPLAUSIBLE = "implausible"
FLAG_ANOMALY = "anomaly_unconfirmed"
FLAG_FROZEN = "frozen_suspect"
FLAG_IMPUTED = "imputed"


def reset_derived(frame: pd.DataFrame) -> pd.DataFrame:
    """Restaura o estado da fonte: tira imputações e marcas das execuções anteriores."""
    out = frame.copy()
    imputed = out["is_imputed"].fillna(False).astype(bool)
    out.loc[imputed, OHLC] = np.nan
    out["is_imputed"] = False
    out["quality_flag"] = pd.Series([""] * len(out), index=out.index, dtype="string")
    out["is_valid"] = out[OHLC].notna().all(axis=1)
    return out


def flag_implausible(frame: pd.DataFrame, qcfg: Mapping[str, Any]) -> pd.DataFrame:
    lo, hi = qcfg["plausibility"]["min_price"], qcfg["plausibility"]["max_price"]
    v = frame["is_valid"]
    bad = v & (
        (frame[OHLC] <= 0).any(axis=1)
        | (frame[OHLC] < lo).any(axis=1)
        | (frame[OHLC] > hi).any(axis=1)
        | (frame["high"] < frame["low"])
        | (frame["close"] > frame["high"])
        | (frame["close"] < frame["low"])
        | (frame["open"] > frame["high"])
        | (frame["open"] < frame["low"])
    )
    frame.loc[bad, "is_valid"] = False
    frame.loc[bad, "quality_flag"] = FLAG_IMPLAUSIBLE
    return frame


def flag_anomalies(
    frame: pd.DataFrame,
    in_session: pd.Series,
    qcfg: Mapping[str, Any],
    ewma_lambda: float,
    step_seconds: int = 300,
    warmup: int = 20,
) -> pd.DataFrame:
    """Retorno de 5 min com |r| > max(k·σ_EWMA de 5 min, mínimo %) (seção 6).

    Só retornos entre candles válidos do pregão separados por exatamente um intervalo:
    o salto entre fechamento e abertura não é um retorno de 5 min. σ usa só retornos
    anteriores. O retorno é medido contra o candle anterior, rejeitado ou não, para que
    um salto real não contamine os candles seguintes.
    """
    k = float(qcfg["anomaly"]["sigma_multiple"])
    min_abs = float(qcfg["anomaly"]["min_abs_return_pct"]) / 100.0
    mask = frame["is_valid"] & in_session
    idx = frame.index[mask]
    if len(idx) < warmup + 2:
        return frame
    closes = frame.loc[idx, "close"].to_numpy()
    times = frame.loc[idx, "event_time"]
    gaps = times.diff().dt.total_seconds().to_numpy()[1:]
    rets = np.diff(np.log(closes))
    var = np.nan
    seen = 0
    for i, r in enumerate(rets):
        if gaps[i] != step_seconds:
            continue
        if seen >= warmup and np.isfinite(var):
            limit = max(k * np.sqrt(var), min_abs)
            if abs(r) > limit:
                row = idx[i + 1]
                frame.loc[row, "is_valid"] = False
                frame.loc[row, "quality_flag"] = FLAG_ANOMALY
                continue
        var = r * r if not np.isfinite(var) else ewma_lambda * var + (1 - ewma_lambda) * r * r
        seen += 1
    return frame


def flag_frozen(frame: pd.DataFrame, in_session: pd.Series, run_length: int) -> pd.DataFrame:
    """Marca como suspeito o trecho com >= ``run_length`` closes idênticos no pregão."""
    mask = frame["is_valid"] & in_session
    sub = frame.loc[mask, "close"]
    if sub.empty:
        return frame
    group = (sub != sub.shift()).cumsum()
    sizes = group.map(group.value_counts())
    suspect = sizes[sizes >= run_length].index
    empty = frame.loc[suspect, "quality_flag"] == ""
    frame.loc[suspect[empty.to_numpy()], "quality_flag"] = FLAG_FROZEN
    return frame


def impute_short_gaps(
    frame: pd.DataFrame, in_session: pd.Series, max_consecutive: int
) -> pd.DataFrame:
    """Lacunas de até ``max_consecutive`` candles no pregão, entre candles válidos,
    recebem o último close (OHLC = close anterior) e ficam ``is_imputed``."""
    invalid = ~frame["is_valid"] & in_session
    last_close = frame["close"].where(frame["is_valid"]).ffill()
    valid_time = frame["event_time"].where(frame["is_valid"])
    day = frame["event_time"].dt.date
    prev_same_day = valid_time.ffill().dt.date == day
    next_same_day = valid_time.bfill().dt.date == day
    run_id = (invalid != invalid.shift()).cumsum()
    run_len = invalid.groupby(run_id).transform("sum")
    fill = invalid & (run_len <= max_consecutive) & prev_same_day & next_same_day
    for col in OHLC:
        frame.loc[fill, col] = last_close[fill]
    frame.loc[fill, "is_imputed"] = True
    frame.loc[fill & (frame["quality_flag"] == ""), "quality_flag"] = FLAG_IMPUTED
    return frame


def apply_candle_rules(
    frame: pd.DataFrame,
    in_session: pd.Series | None,
    qcfg: Mapping[str, Any],
    ewma_lambda: float,
    interval: str,
) -> pd.DataFrame:
    """1m: só plausibilidade (arquivo de auditoria). 5m: todas as regras da seção 6.
    1h: plausibilidade e lacunas (mudança anormal e feed congelado são regras de 5 min)."""
    frame = frame.sort_values("event_time").reset_index(drop=True)
    frame = reset_derived(frame)
    frame = flag_implausible(frame, qcfg)
    if in_session is None or interval == "1m":
        return frame
    in_session = in_session.reset_index(drop=True)
    if interval == "5m":
        frame = flag_anomalies(frame, in_session, qcfg, ewma_lambda)
        frame = flag_frozen(frame, in_session, int(qcfg["frozen_feed"]["identical_closes_5m"]))
    max_gap = int(qcfg["missing"]["impute_max_consecutive"])
    return impute_short_gaps(frame, in_session, max_gap)
