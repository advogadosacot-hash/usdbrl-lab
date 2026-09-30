import gzip
import json
from datetime import date

import pandas as pd
from synthetic import candles_frame, response

from usdbrl_lab.storage.layout import market_data_file, symbol_slug
from usdbrl_lab.storage.ops_io import append_jsonl, write_raw_payloads
from usdbrl_lab.storage.parquet_io import last_event_time, merge_rows, read_days, write_days


def _frame(times, closes, run="r1"):
    f = candles_frame(times, closes)
    f["ingested_at"] = pd.Timestamp("2026-10-05 20:00Z")
    f["run_id"] = run
    return f


def test_symbol_slug_and_layout(tmp_path):
    assert symbol_slug("BRL=X") == "brl_x"
    p = market_data_file(tmp_path, "BRL=X", "5m", date(2026, 10, 5))
    assert p.as_posix().endswith("market_data/brl_x/5m/2026/10/05.parquet")


def test_roundtrip_preserves_utc_and_partitions_by_day(tmp_path):
    f = _frame(["2026-10-05 20:55Z", "2026-10-06 12:00Z"], [4.0, 4.1])
    written = write_days(tmp_path, "BRL=X", "5m", f)
    assert len(written) == 2
    back = read_days(tmp_path, "BRL=X", "5m")
    assert str(back["event_time"].dt.tz) == "UTC"
    assert back["close"].tolist() == [4.0, 4.1]
    assert last_event_time(tmp_path, "BRL=X", "5m") == pd.Timestamp("2026-10-06 12:00Z")


def test_unchanged_data_is_not_rewritten(tmp_path):
    f = _frame(["2026-10-05 14:00Z", "2026-10-05 14:05Z"], [4.0, 4.1])
    write_days(tmp_path, "BRL=X", "5m", f)
    again = _frame(["2026-10-05 14:00Z", "2026-10-05 14:05Z"], [4.0, 4.1], run="r2")
    merged, revised = merge_rows(read_days(tmp_path, "BRL=X", "5m"), again)
    assert revised == 0
    assert merged["run_id"].tolist() == ["r1", "r1"]  # linha antiga mantida
    assert write_days(tmp_path, "BRL=X", "5m", merged) == []


def test_revision_takes_new_value_keeps_earliest_available_time(tmp_path):
    old = _frame(["2026-10-05 14:00Z"], [4.0])
    new = _frame(["2026-10-05 14:00Z"], [4.2], run="r2")
    new["available_time"] = new["available_time"] + pd.Timedelta(hours=1)
    merged, revised = merge_rows(old, new)
    assert revised == 1
    assert merged["close"].iloc[0] == 4.2
    assert merged["available_time"].iloc[0] == old["available_time"].iloc[0]


def test_new_rows_are_appended_sorted():
    old = _frame(["2026-10-05 14:05Z"], [4.1])
    new = _frame(["2026-10-05 14:00Z", "2026-10-05 14:10Z"], [4.0, 4.2])
    merged, _ = merge_rows(old, new)
    assert merged["close"].tolist() == [4.0, 4.1, 4.2]


def test_ops_jsonl_and_raw_gz(tmp_path):
    p = append_jsonl(tmp_path, "runs", date(2026, 10, 5), {"run_id": "a"})
    append_jsonl(tmp_path, "runs", date(2026, 10, 5), {"run_id": "b"})
    assert [json.loads(line)["run_id"] for line in p.read_text().splitlines()] == ["a", "b"]
    raw = write_raw_payloads(
        tmp_path,
        "yahoo",
        date(2026, 10, 5),
        "r1",
        [response(b'{"ok": 1}', params={"interval": "5m"})],
    )
    doc = json.loads(gzip.decompress(raw.read_bytes()))
    assert doc[0]["body"] == {"ok": 1} and doc[0]["params"] == {"interval": "5m"}
