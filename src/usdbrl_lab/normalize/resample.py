"""Reamostragem de candles (seção 5, regra 3).

open = primeiro open válido, high = máximo, low = mínimo, close = último close válido;
agregado com menos de ``min_valid_fraction`` dos subcandles válidos fica ``is_incomplete``.
"""

from __future__ import annotations

import pandas as pd

from usdbrl_lab.sources.yahoo import INTERVAL_SECONDS


def resample_candles(
    frame: pd.DataFrame, source_interval: str, target_interval: str, min_valid_fraction: float
) -> pd.DataFrame:
    step_src = INTERVAL_SECONDS[source_interval]
    step_dst = INTERVAL_SECONDS[target_interval]
    if step_dst % step_src:
        raise ValueError("intervalo de destino precisa ser múltiplo do de origem")
    expected = step_dst // step_src
    cols = ["event_time", "open", "high", "low", "close", "is_valid"]
    if frame.empty:
        return pd.DataFrame(columns=[*cols, "n_valid", "is_incomplete"])
    valid = frame.loc[frame["is_valid"], ["event_time", "open", "high", "low", "close"]].copy()
    valid["bucket"] = valid["event_time"].dt.floor(f"{step_dst}s")
    grouped = valid.sort_values("event_time").groupby("bucket")
    out = pd.DataFrame(
        {
            "open": grouped["open"].first(),
            "high": grouped["high"].max(),
            "low": grouped["low"].min(),
            "close": grouped["close"].last(),
            "n_valid": grouped["close"].size(),
        }
    )
    out.index.name = "event_time"
    out = out.reset_index()
    out["is_valid"] = True
    out["is_incomplete"] = out["n_valid"] < min_valid_fraction * expected
    return out
