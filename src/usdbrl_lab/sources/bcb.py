"""BCB PTAX (Olinda OData): referência oficial diária.

A PTAX é média de janelas de consulta, não último negócio: serve para conferência e
exibição, nunca como substituta dos candles intraday do Yahoo.
"""

from __future__ import annotations

import json
from datetime import date
from zoneinfo import ZoneInfo

import pandas as pd

from usdbrl_lab.sources.base import FetchResult, HttpGet, SourceError

SOURCE = "bcb_ptax"
SYMBOL = "ptax_usd"
INTERVAL = "bulletin"


def parse_ptax(body: bytes, local_tz: str) -> pd.DataFrame:
    try:
        doc = json.loads(body)
    except (ValueError, UnicodeDecodeError) as exc:
        raise SourceError("parse", "resposta da PTAX não é JSON válido") from exc
    rows = doc.get("value")
    if rows is None:
        raise SourceError("parse", "resposta da PTAX sem campo 'value'")
    columns = ["event_time", "bulletin_type", "bid", "ask"]
    if not rows:
        return pd.DataFrame(columns=columns)
    frame = pd.DataFrame(rows)
    local = pd.to_datetime(frame["dataHoraCotacao"], format="ISO8601")
    event_time = local.dt.tz_localize(ZoneInfo(local_tz)).dt.tz_convert("UTC")
    return pd.DataFrame(
        {
            "event_time": event_time,
            "bulletin_type": frame["tipoBoletim"].astype("string"),
            "bid": pd.to_numeric(frame["cotacaoCompra"], errors="coerce"),
            "ask": pd.to_numeric(frame["cotacaoVenda"], errors="coerce"),
        }
    ).sort_values("event_time", ignore_index=True)


class PtaxSource:
    def __init__(self, http_get: HttpGet, base_url: str, currency: str, local_tz: str) -> None:
        self._get = http_get
        self._base_url = base_url
        self._currency = currency
        self._tz = local_tz

    def fetch(self, start: date, end: date) -> FetchResult:
        url = (
            self._base_url + "CotacaoMoedaPeriodo(moeda=@moeda,dataInicial=@dataInicial,"
            "dataFinalCotacao=@dataFinalCotacao)"
        )
        params = {
            "@moeda": f"'{self._currency}'",
            "@dataInicial": f"'{start:%m-%d-%Y}'",
            "@dataFinalCotacao": f"'{end:%m-%d-%Y}'",
            "$format": "json",
        }
        response = self._get(url, params)
        frame = parse_ptax(response.body, self._tz)
        return FetchResult(SOURCE, SYMBOL, INTERVAL, frame, [response])
