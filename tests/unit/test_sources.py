import json
from datetime import UTC, date, datetime, timedelta

import pandas as pd
import pytest
from synthetic import ptax_payload, response, yahoo_payload

from usdbrl_lab.sources.base import SourceError
from usdbrl_lab.sources.bcb import PtaxSource, parse_ptax
from usdbrl_lab.sources.yahoo import YahooSource, parse_chart


def test_yahoo_parse_utc_nulls_and_unaligned():
    t0 = int(datetime(2026, 10, 5, 12, 0, tzinfo=UTC).timestamp())
    ts = [t0, t0 + 300, t0 + 600, t0 + 601]  # último = candle "ao vivo" desalinhado
    frame, dropped = parse_chart(yahoo_payload(ts, [4.0, None, 4.01, 4.02]), "5m")
    assert dropped == 1
    assert len(frame) == 3
    assert str(frame["event_time"].dt.tz) == "UTC"
    assert frame["event_time"].iloc[0] == pd.Timestamp("2026-10-05 12:00", tz="UTC")
    assert frame["close"].isna().tolist() == [False, True, False]  # nulo não vira zero


def test_yahoo_error_payload_raises_without_body():
    body = json.dumps(
        {"chart": {"result": None, "error": {"code": "Not Found", "description": "4.1234"}}}
    ).encode()
    with pytest.raises(SourceError) as exc:
        parse_chart(body, "5m")
    assert "4.1234" not in str(exc.value)


def test_yahoo_invalid_json():
    with pytest.raises(SourceError, match="JSON"):
        parse_chart(b"<html>", "5m")


def test_yahoo_fetch_period_chunks_requests():
    calls = []

    def http_get(url, params):
        calls.append(params)
        return response(yahoo_payload([params["period1"] - params["period1"] % 60], [4.0]))

    src = YahooSource(http_get, "https://example.invalid/chart/", "BRL=X")
    end = datetime(2026, 10, 5, tzinfo=UTC)
    res = src.fetch_period("1m", end - timedelta(days=29), end, chunk_days=7)
    assert len(calls) == 5
    assert all(c["period2"] - c["period1"] <= 7 * 86400 for c in calls)
    assert res.frame["event_time"].is_monotonic_increasing


def test_ptax_converts_brasilia_to_utc():
    body = ptax_payload([("2026-09-28 13:03:11.35885", "Fechamento", 4.1, 4.2)])
    frame = parse_ptax(body, "America/Sao_Paulo")
    assert frame["event_time"].iloc[0] == pd.Timestamp("2026-09-28 16:03:11.35885", tz="UTC")
    assert frame["bulletin_type"].iloc[0] == "Fechamento"


def test_ptax_empty_and_malformed():
    assert parse_ptax(ptax_payload([]), "America/Sao_Paulo").empty
    with pytest.raises(SourceError):
        parse_ptax(b"{}", "America/Sao_Paulo")


def test_ptax_request_format():
    seen = {}

    def http_get(url, params):
        seen.update(url=url, params=params)
        return response(ptax_payload([]))

    PtaxSource(http_get, "https://example.invalid/odata/", "USD", "America/Sao_Paulo").fetch(
        date(2026, 9, 1), date(2026, 9, 30)
    )
    assert "CotacaoMoedaPeriodo" in seen["url"]
    assert seen["params"]["@dataInicial"] == "'09-01-2026'"
    assert seen["params"]["@moeda"] == "'USD'"
