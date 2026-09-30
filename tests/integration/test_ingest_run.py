"""Execução completa de ``run_ingest`` com fontes falsas (dados sintéticos)."""

import json
import math
from datetime import UTC, date, datetime, timedelta

import pytest
from synthetic import ptax_payload, response, yahoo_payload

from usdbrl_lab.ingest.run import run_ingest
from usdbrl_lab.sources.base import SourceError
from usdbrl_lab.storage.parquet_io import read_days

NOW = datetime(2026, 10, 7, 15, 0, tzinfo=UTC)  # quarta-feira, pregão aberto
STEP = {"1m": 60, "5m": 300, "1h": 3600}


def _mdy(value: str) -> date:
    month, day, year = value.strip("'").split("-")
    return date(int(year), int(month), int(day))


def synthetic_price(ts: int) -> float:
    return round(4.0 + 0.01 * math.sin(ts / 5000.0), 6)


class FakeSources:
    def __init__(self, yahoo_down=False):
        self.yahoo_down = yahoo_down
        self.prices: set[str] = set()

    def __call__(self, url, params):
        if "CotacaoMoedaPeriodo" in url:
            start = _mdy(params["@dataInicial"])
            end = _mdy(params["@dataFinalCotacao"])
            rows, d = [], start
            while d <= end:
                if d.weekday() < 5:
                    rows.append((f"{d} 13:03:11.358", "Fechamento", 4.0, 4.001))
                d += timedelta(days=1)
            return response(ptax_payload(rows), url, params)
        if self.yahoo_down:
            raise SourceError("http", "HTTP 503", 503)
        step = STEP[params["interval"]]
        if "range" in params:
            p1, p2 = int((NOW - timedelta(days=60)).timestamp()), int(NOW.timestamp())
        else:
            p1, p2 = params["period1"], params["period2"]
        ts, closes = [], []
        t = p1 - p1 % step
        while t <= p2:
            dt = datetime.fromtimestamp(t, UTC)
            if dt.weekday() < 5 and 12 <= dt.hour < 21:
                ts.append(t)
                price = synthetic_price(t)
                closes.append(price)
                self.prices.add(f"{price}")
            t += step
        return response(yahoo_payload(ts, closes), url, params)


@pytest.fixture
def data_dir(tmp_path):
    d = tmp_path / "usdbrl-data"
    d.mkdir()
    return d


def test_full_run_writes_market_data_quality_and_ops(data_dir):
    fake = FakeSources()
    summary = run_ingest(data_dir, backfill=True, now=NOW, http_get=fake, run_id="t1")
    assert summary["status"] == "ok"
    for interval in ("1m", "5m", "1h"):
        assert summary["intervals"][interval]["status"] == "ok"
        assert not read_days(data_dir, "BRL=X", interval).empty
    assert summary["quality"]["decision"] == "normal"
    assert (data_dir / "market_data" / "ptax_usd" / "bulletin").exists()
    today = f"{NOW:%Y/%m/%d}"
    assert (data_dir / "ops" / "runs" / f"{today}.jsonl").exists()
    assert (data_dir / "ops" / "data_quality" / f"{today}.jsonl").exists()
    assert (data_dir / "raw" / "yahoo" / today / "t1.json.gz").exists()


def test_summary_printed_to_public_log_has_no_prices(data_dir):
    fake = FakeSources()
    summary = run_ingest(data_dir, backfill=True, now=NOW, http_get=fake, run_id="t1")
    text = json.dumps(summary, default=str)
    assert not [p for p in fake.prices if p in text]


def test_second_run_is_idempotent(data_dir):
    run_ingest(data_dir, backfill=True, now=NOW, http_get=FakeSources(), run_id="t1")
    again = run_ingest(data_dir, now=NOW, http_get=FakeSources(), run_id="t2")
    for interval in ("1m", "5m", "1h"):
        assert again["intervals"][interval]["files_written"] == 0
        assert again["intervals"][interval]["revised_rows"] == 0
    assert again["ptax"]["files_written"] == 0


def test_yahoo_down_means_no_usable_data_and_is_recorded(data_dir):
    summary = run_ingest(data_dir, now=NOW, http_get=FakeSources(yahoo_down=True), run_id="t3")
    assert summary["status"] == "failed"
    assert summary["quality"]["decision"] == "blocked"
    assert all(v["status"] == "failed" for v in summary["intervals"].values())
    record = json.loads(
        (data_dir / "ops" / "data_quality" / f"{NOW:%Y/%m/%d}.jsonl").read_text().splitlines()[-1]
    )
    assert record["decision"] == "blocked"
    assert record["source_used"] is None
    assert not (data_dir / "market_data" / "brl_x").exists()


def test_ptax_is_never_used_as_intraday_price(data_dir):
    run_ingest(data_dir, now=NOW, http_get=FakeSources(yahoo_down=True), run_id="t4")
    assert (data_dir / "market_data" / "ptax_usd").exists()
    assert read_days(data_dir, "BRL=X", "5m").empty
    assert date(2026, 10, 7).weekday() == 2
