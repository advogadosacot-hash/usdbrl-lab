"""Cliente HTTP com timeout e novas tentativas (seção 6: 20 s; esperas 2, 8, 30 s).

HTTP 429/5xx e falhas de rede tentam de novo; outros 4xx falham na hora.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from typing import Any

import requests

from usdbrl_lab.common.clock import utc_now
from usdbrl_lab.sources.base import HttpResponse, SourceError

USER_AGENT = "Mozilla/5.0 (compatible; usdbrl-lab/0.1)"
MAX_BODY_BYTES = 50 * 1024 * 1024


def make_http_get(
    timeout_s: float,
    retry_waits_s: Sequence[float],
    retry_on_status: Sequence[int],
    session: requests.Session | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> Callable[[str, dict[str, Any]], HttpResponse]:
    sess = session or requests.Session()
    # requests já define "python-requests/x", que o Yahoo responde com HTTP 429.
    sess.headers["User-Agent"] = USER_AGENT
    retry_status = set(retry_on_status)

    def http_get(url: str, params: dict[str, Any]) -> HttpResponse:
        attempts = len(retry_waits_s) + 1
        last_error: SourceError | None = None
        for attempt in range(attempts):
            if attempt:
                sleep(retry_waits_s[attempt - 1])
            started = time.monotonic()
            try:
                resp = sess.get(url, params=params, timeout=timeout_s)
            except requests.Timeout:
                last_error = SourceError("timeout", f"timeout após {timeout_s:.0f} s")
                continue
            except requests.RequestException as exc:
                last_error = SourceError("network", f"falha de rede: {type(exc).__name__}")
                continue
            if resp.status_code in retry_status:
                last_error = SourceError("http", f"HTTP {resp.status_code}", resp.status_code)
                continue
            if resp.status_code >= 400:
                raise SourceError("http", f"HTTP {resp.status_code}", resp.status_code)
            body = resp.content
            if len(body) > MAX_BODY_BYTES:
                raise SourceError("parse", "resposta maior que o limite permitido")
            return HttpResponse(
                url=url,
                params=dict(params),
                status=resp.status_code,
                body=body,
                latency_s=round(time.monotonic() - started, 3),
                fetched_at=utc_now(),
            )
        raise last_error or SourceError("network", "nenhuma tentativa realizada")

    return http_get
