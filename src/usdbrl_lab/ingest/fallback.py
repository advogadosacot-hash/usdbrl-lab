"""Cadeia de fallback do preço-alvo (seção 6; P4, P6).

A ordem vem de ``sources.price_fallback_order`` (V1: só ``yahoo``). Se nenhuma fonte da
cadeia entregar dados, o resultado é ``None`` e o sistema fica em "sem dado utilizável" —
nunca se improvisa outra fonte.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any

from usdbrl_lab.sources.base import FetchResult, SourceError


def fetch_with_fallback(
    chain: Sequence[str], fetchers: Mapping[str, Callable[[], FetchResult]]
) -> tuple[FetchResult | None, str | None, list[dict[str, Any]]]:
    attempts: list[dict[str, Any]] = []
    for name in chain:
        fetch = fetchers.get(name)
        if fetch is None:
            attempts.append({"source": name, "status": "not_available"})
            continue
        try:
            result = fetch()
        except SourceError as exc:
            attempts.append(
                {"source": name, "status": "failed", "kind": exc.kind, "message": str(exc)}
            )
            continue
        attempts.append({"source": name, "status": "ok"})
        return result, name, attempts
    return None, None, attempts
