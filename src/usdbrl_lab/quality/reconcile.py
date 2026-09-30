"""Conferências cruzadas que geram alertas (não bloqueiam):

- 1 h nativo do Yahoo × 1 h reamostrado do 5 min (seção 5: "os dois devem coincidir");
- close diário do Yahoo × PTAX de fechamento (seção 6: > 1,5% = alerta).

Os resultados vão só para o registro privado de qualidade; não contêm preços.
"""

from __future__ import annotations

import pandas as pd

from usdbrl_lab.normalize.resample import resample_candles


def native_vs_resampled_1h(
    five_min: pd.DataFrame,
    one_hour: pd.DataFrame,
    in_session_5m: pd.Series,
    min_valid_fraction: float,
    threshold_pct: float,
) -> dict:
    session = five_min.loc[in_session_5m.to_numpy()]
    res = resample_candles(session, "5m", "1h", min_valid_fraction)
    res = res.loc[~res["is_incomplete"]]
    native = one_hour.loc[one_hour["is_valid"], ["event_time", "close"]]
    joined = res[["event_time", "close"]].merge(native, on="event_time", suffixes=("_res", "_nat"))
    if joined.empty:
        return {"compared_hours": 0, "divergent_hours": 0, "max_divergence_pct": None}
    diff = (joined["close_res"] / joined["close_nat"] - 1).abs() * 100
    return {
        "compared_hours": int(len(joined)),
        "divergent_hours": int((diff > threshold_pct).sum()),
        "max_divergence_pct": round(float(diff.max()), 4),
    }


def yahoo_vs_ptax(
    five_min: pd.DataFrame,
    in_session_5m: pd.Series,
    ptax: pd.DataFrame,
    closing_bulletin: str,
    alert_pct: float,
) -> dict:
    session = five_min.loc[in_session_5m.to_numpy() & five_min["is_valid"].to_numpy()]
    if session.empty or ptax.empty:
        return {"compared_days": 0, "alert_days": []}
    daily = session.groupby(session["event_time"].dt.date)["close"].last()
    closing = ptax.loc[ptax["bulletin_type"] == closing_bulletin].copy()
    closing["day"] = closing["event_time"].dt.tz_convert("America/Sao_Paulo").dt.date
    mid = closing.groupby("day").apply(lambda g: float(((g["bid"] + g["ask"]) / 2).iloc[-1]))
    both = pd.concat({"yahoo": daily, "ptax": mid}, axis=1).dropna()
    if both.empty:
        return {"compared_days": 0, "alert_days": []}
    diff = (both["yahoo"] / both["ptax"] - 1).abs() * 100
    alerts = [str(d) for d in diff.index[diff > alert_pct]]
    return {
        "compared_days": int(len(both)),
        "alert_days": alerts,
        "max_divergence_pct": round(float(diff.max()), 4),
    }
