"""Índice de qualidade Q (seção 6): mínimo dos componentes disponíveis.

Componente de consistência entre fontes: sem segunda fonte intraday na V1, ele é
registrado como indisponível (``None``) e não entra no mínimo — ver decisão pendente
informada no relatório da fase 1. Nenhuma previsão usa Q antes da fase 6.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from typing import Any

import pandas as pd

from usdbrl_lab.quality.checks import FLAG_ANOMALY, FLAG_FROZEN, FLAG_IMPLAUSIBLE


@dataclass
class QualityScore:
    decision: str  # normal | degraded | blocked | market_closed
    q: float | None
    components: dict[str, float | None]
    reasons: list[str] = field(default_factory=list)
    stale_minutes: float | None = None
    missing_last_window: float | None = None
    max_consecutive_missing: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _level(ok: bool, degraded: bool, s: Mapping[str, Any]) -> float:
    if not ok:
        return float(s["component_blocked"])
    return float(s["component_degraded"]) if degraded else float(s["component_ok"])


def score_5m(
    frame: pd.DataFrame,
    in_session: pd.Series,
    now: pd.Timestamp,
    market_open_now: bool,
    source_mode: str | None,
    qcfg: Mapping[str, Any],
) -> QualityScore:
    s = qcfg["score"]
    if source_mode is None:
        return QualityScore("blocked", 0.0, {"source": 0.0}, ["fonte principal indisponível"])
    if not market_open_now:
        return QualityScore("market_closed", None, {}, ["mercado fechado"])

    today = frame.loc[in_session & (frame["event_time"].dt.date == now.date())]
    if not today["is_valid"].any():
        # Dia útil sem candle válido no pregão: feriado detectado pelos dados (seção 5).
        return QualityScore("market_closed", None, {}, ["nenhum candle válido hoje no pregão"])

    reasons: list[str] = []
    last_valid = today.loc[today["is_valid"], "event_time"].max()
    stale = (now - (last_valid + pd.Timedelta(minutes=5))).total_seconds() / 60.0
    extra, block = qcfg["stale"]["extra_minutes"], qcfg["stale"]["block_minutes"]
    fresh = _level(stale <= block, stale > 5 + extra, s)
    if fresh < 1:
        reasons.append(f"último candle válido há {stale:.0f} min")

    window = qcfg["missing"]["degrade_window_bars"]
    recent = today.tail(window)
    missing = ~recent["is_valid"]
    frac = float(missing.mean()) if len(recent) else 0.0
    runs = missing.groupby((missing != missing.shift()).cumsum()).sum()
    max_run = int(runs.max()) if len(runs) else 0
    complete = _level(
        frac <= qcfg["missing"]["block_fraction"],
        frac > qcfg["missing"]["degrade_fraction"] or max_run >= 3,
        s,
    )
    if complete < 1:
        reasons.append(f"{frac:.0%} dos últimos {len(recent)} candles ausentes")

    flags = recent["quality_flag"].astype(str)
    rejected = flags.isin([FLAG_IMPLAUSIBLE, FLAG_ANOMALY]).any()
    frozen = (flags == FLAG_FROZEN).any()
    plaus = _level(True, bool(rejected or frozen), s)
    if plaus < 1:
        reasons.append("candles rejeitados ou feed congelado na janela recente")

    source = float(s["close_only_max"]) if source_mode == "close_only" else float(s["component_ok"])
    components: dict[str, float | None] = {
        "freshness": fresh,
        "completeness": complete,
        "plausibility": plaus,
        "source": source,
        "consistency": None,  # sem segunda fonte intraday na V1
    }
    q = min(v for v in components.values() if v is not None)
    if q >= s["normal_min"]:
        decision = "normal"
    elif q >= s["publish_min"]:
        decision = "degraded"
    else:
        decision = "blocked"
    return QualityScore(decision, q, components, reasons, round(stale, 1), round(frac, 3), max_run)
