"""Tipos comuns a todas as fontes.

Mensagens de erro nunca incluem o corpo da resposta: os logs do repositório público
não podem conter preços do Yahoo (D2).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import pandas as pd


class SourceError(RuntimeError):
    """Falha de uma fonte. ``kind``: timeout, http, network, parse, empty."""

    def __init__(self, kind: str, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.kind = kind
        self.status = status


@dataclass(frozen=True)
class HttpResponse:
    url: str  # sem parâmetros sensíveis
    params: dict[str, Any]
    status: int
    body: bytes
    latency_s: float
    fetched_at: datetime


# Assinatura do cliente HTTP injetado nas fontes (implementado em ingest/retry.py).
HttpGet = Callable[[str, dict[str, Any]], HttpResponse]


@dataclass
class FetchResult:
    source: str
    symbol: str
    interval: str
    frame: pd.DataFrame
    responses: list[HttpResponse] = field(default_factory=list)
    dropped_unaligned: int = 0
