"""Construtores de dados SINTÉTICOS no formato das fontes (nenhum dado real do Yahoo, D2)."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import numpy as np
import pandas as pd

from usdbrl_lab.sources.base import HttpResponse

BASE_PRICE = 4.0  # nível artificial, longe do real


def yahoo_payload(timestamps, closes, spread=0.001):
    """JSON no formato do endpoint de gráfico; close None vira candle vazio."""

    def shifted(sign):
        return [None if c is None else round(c + sign * spread, 6) for c in closes]

    return json.dumps(
        {
            "chart": {
                "result": [
                    {
                        "meta": {"symbol": "BRL=X"},
                        "timestamp": [int(t) for t in timestamps],
                        "indicators": {
                            "quote": [
                                {
                                    "open": closes,
                                    "high": shifted(+1),
                                    "low": shifted(-1),
                                    "close": closes,
                                    "volume": [0] * len(closes),
                                }
                            ]
                        },
                    }
                ],
                "error": None,
            }
        }
    ).encode()


def session_timestamps(day: datetime, step_s: int, start_h=12, end_h=21):
    t0 = day.replace(hour=start_h, minute=0, second=0, microsecond=0, tzinfo=UTC)
    n = (end_h - start_h) * 3600 // step_s
    return [int((t0 + timedelta(seconds=i * step_s)).timestamp()) for i in range(n)]


def random_walk(n, seed=0, sigma=0.0004, start=BASE_PRICE):
    rng = np.random.default_rng(seed)
    return [float(x) for x in np.round(start * np.exp(np.cumsum(rng.normal(0, sigma, n))), 6)]


def ptax_payload(rows):
    """rows: [("2026-09-28 13:03:11.35885", "Fechamento", bid, ask), ...]"""
    return json.dumps(
        {
            "value": [
                {
                    "paridadeCompra": 1.0,
                    "paridadeVenda": 1.0,
                    "cotacaoCompra": bid,
                    "cotacaoVenda": ask,
                    "dataHoraCotacao": ts,
                    "tipoBoletim": kind,
                }
                for ts, kind, bid, ask in rows
            ]
        }
    ).encode()


def response(body: bytes, url="https://example.invalid/x", params=None, status=200):
    return HttpResponse(url, dict(params or {}), status, body, 0.01, datetime.now(UTC))


def candles_frame(times, closes, spread=0.001):
    """DataFrame canônico mínimo para testes de qualidade e armazenamento."""
    closes = pd.Series(closes, dtype="float64")
    frame = pd.DataFrame(
        {
            "event_time": pd.to_datetime(times, utc=True),
            "open": closes,
            "high": closes + spread,
            "low": closes - spread,
            "close": closes,
        }
    )
    frame["is_valid"] = frame[["open", "high", "low", "close"]].notna().all(axis=1)
    frame["is_imputed"] = False
    frame["quality_flag"] = pd.Series([""] * len(frame), dtype="string")
    frame["available_time"] = frame["event_time"] + pd.Timedelta(minutes=7)
    return frame
