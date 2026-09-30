"""Yahoo Finance, endpoint de gráfico (BRL=X). Fonte principal do preço-alvo intraday.

Uso pessoal; dados brutos só no repositório privado (D2, P1). O adaptador é isolado atrás
de ``fetch`` para permitir trocar a fonte por uma licenciada (D3).
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta

import pandas as pd

from usdbrl_lab.common.clock import ensure_utc
from usdbrl_lab.sources.base import FetchResult, HttpGet, SourceError

SOURCE = "yahoo"
INTERVAL_SECONDS = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600}
OHLC = ["open", "high", "low", "close"]


def parse_chart(body: bytes, interval: str) -> tuple[pd.DataFrame, int]:
    """Converte a resposta do endpoint em candles (UTC, rotulados pelo início).

    Devolve também quantas linhas foram descartadas por não estarem alinhadas à grade
    (o candle "ao vivo" vem com timestamp quebrado, ex.: 19:14:01).
    """
    try:
        doc = json.loads(body)
    except (ValueError, UnicodeDecodeError) as exc:
        raise SourceError("parse", "resposta do Yahoo não é JSON válido") from exc
    chart = doc.get("chart") or {}
    if chart.get("error"):
        code = (chart["error"] or {}).get("code", "desconhecido")
        raise SourceError("parse", f"Yahoo devolveu erro: {code}")
    results = chart.get("result") or []
    if not results:
        raise SourceError("empty", "Yahoo não devolveu resultado")
    result = results[0]
    timestamps = result.get("timestamp") or []
    empty = pd.DataFrame(columns=["event_time", *OHLC])
    if not timestamps:
        return empty.astype({c: "float64" for c in OHLC}), 0
    quotes = ((result.get("indicators") or {}).get("quote") or [{}])[0]
    frame = pd.DataFrame(
        {
            "event_time": pd.to_datetime(timestamps, unit="s", utc=True),
            **{
                c: pd.to_numeric(
                    pd.Series(quotes.get(c) or [None] * len(timestamps)), errors="coerce"
                ).astype("float64")
                for c in OHLC
            },
        }
    )
    step = INTERVAL_SECONDS[interval]
    # Usa os segundos originais: não depende da resolução interna do pandas.
    aligned = pd.Series([int(t) % step == 0 for t in timestamps])
    dropped = int((~aligned).sum())
    frame = frame.loc[aligned].reset_index(drop=True)
    return frame, dropped


class YahooSource:
    def __init__(self, http_get: HttpGet, base_url: str, symbol: str) -> None:
        self._get = http_get
        self._base_url = base_url
        self.symbol = symbol

    def _call(self, interval: str, params: dict) -> tuple[pd.DataFrame, int, object]:
        response = self._get(self._base_url + self.symbol, {"interval": interval, **params})
        frame, dropped = parse_chart(response.body, interval)
        return frame, dropped, response

    def fetch_period(
        self, interval: str, start: datetime, end: datetime, chunk_days: int
    ) -> FetchResult:
        """Busca [start, end] em blocos de ``chunk_days`` (limite do Yahoo por consulta)."""
        start, end = ensure_utc(start), ensure_utc(end)
        frames, responses, dropped = [], [], 0
        cursor = start
        while cursor < end:
            stop = min(cursor + timedelta(days=chunk_days), end)
            frame, n_drop, resp = self._call(
                interval, {"period1": int(cursor.timestamp()), "period2": int(stop.timestamp())}
            )
            frames.append(frame)
            responses.append(resp)
            dropped += n_drop
            cursor = stop
        return self._result(interval, frames, responses, dropped)

    def fetch_range(self, interval: str, range_: str) -> FetchResult:
        """Busca por ``range`` (usado no backfill de 1 h: range=730d devolve ~2,8 anos)."""
        frame, dropped, resp = self._call(interval, {"range": range_})
        return self._result(interval, [frame], [resp], dropped)

    def _result(self, interval, frames, responses, dropped) -> FetchResult:
        frame = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
        if not frame.empty:
            frame = frame.drop_duplicates("event_time", keep="last").sort_values("event_time")
            frame = frame.reset_index(drop=True)
        return FetchResult(SOURCE, self.symbol, interval, frame, responses, dropped)
