"""Sessão de mercado em UTC (config/session.toml)."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import time
from typing import Any

import pandas as pd


def _parse_hhmm(value: str) -> time:
    hours, minutes = value.split(":")
    return time(int(hours), int(minutes))


class Session:
    def __init__(self, session_cfg: Mapping[str, Any]) -> None:
        self.open = _parse_hhmm(session_cfg["session"]["open_utc"])
        self.close = _parse_hhmm(session_cfg["session"]["close_utc"])
        self.close_grace_minutes = int(session_cfg["candles"]["close_grace_minutes"])
        self.min_valid_fraction = float(session_cfg["candles"]["resample_min_valid_fraction"])

    def in_session(self, event_time: pd.Series) -> pd.Series:
        """Candle (rotulado pelo início) dentro de [abertura, fechamento) em dia útil."""
        t = event_time.dt.tz_convert("UTC")
        minutes = t.dt.hour * 60 + t.dt.minute
        start = self.open.hour * 60 + self.open.minute
        end = self.close.hour * 60 + self.close.minute
        return (t.dt.dayofweek < 5) & (minutes >= start) & (minutes < end)

    def is_open_at(self, now: pd.Timestamp) -> bool:
        return bool(self.in_session(pd.Series([now]))[0])
