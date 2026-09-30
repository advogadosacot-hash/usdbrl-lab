from datetime import UTC, datetime

import pandas as pd
from synthetic import candles_frame

from usdbrl_lab.normalize.candles import MARKET_DATA_COLUMNS, canonical_candles
from usdbrl_lab.normalize.resample import resample_candles
from usdbrl_lab.normalize.session import Session


def _raw(times, closes):
    f = candles_frame(times, closes)
    return f[["event_time", "open", "high", "low", "close"]]


def _canon(raw, now, backfill=False):
    return canonical_candles(
        raw,
        symbol="BRL=X",
        interval="5m",
        source="yahoo",
        run_id="r1",
        now=now,
        ingested_at=now,
        backfill=backfill,
        close_grace_minutes=2,
    )


def test_open_candle_is_dropped():
    raw = _raw(["2026-10-05 14:00Z", "2026-10-05 14:05Z", "2026-10-05 14:10Z"], [4.0, 4.0, 4.0])
    # 14:10 fecha às 14:15 e só entra a partir de 14:17 (tolerância de 2 min).
    frame, n_open = _canon(raw, datetime(2026, 10, 5, 14, 16, tzinfo=UTC))
    assert n_open == 1
    assert frame["event_time"].max() == pd.Timestamp("2026-10-05 14:05Z")
    assert list(frame.columns) == MARKET_DATA_COLUMNS


def test_available_time_live_vs_backfill():
    raw = _raw(["2026-10-05 14:00Z"], [4.0])
    now = datetime(2026, 10, 5, 18, 0, tzinfo=UTC)
    live, _ = _canon(raw, now)
    back, _ = _canon(raw, now, backfill=True)
    assert live["available_time"].iloc[0] == pd.Timestamp(now)  # instante da coleta
    assert back["available_time"].iloc[0] == pd.Timestamp("2026-10-05 14:07Z")  # fim + 2 min
    assert bool(back["is_backfill"].iloc[0]) is True


def test_null_candle_is_invalid_not_zero():
    raw = _raw(["2026-10-05 14:00Z", "2026-10-05 14:05Z"], [4.0, None])
    frame, _ = _canon(raw, datetime(2026, 10, 5, 16, tzinfo=UTC))
    assert frame["is_valid"].tolist() == [True, False]
    assert frame["close"].isna().iloc[1]


def test_resample_ohlc_rules_and_incomplete():
    times = pd.date_range("2026-10-05 14:00Z", periods=12, freq="5min")
    closes = [4.0 + i * 0.001 for i in range(12)]
    frame = candles_frame(times, closes)
    out = resample_candles(frame, "5m", "1h", 0.8)
    row = out.iloc[0]
    assert row["open"] == closes[0] and row["close"] == closes[-1]
    assert row["high"] == max(closes) + 0.001 and row["low"] == min(closes) - 0.001
    assert not row["is_incomplete"]
    frame.loc[:3, "is_valid"] = False  # 8 de 12 válidos < 80%
    assert resample_candles(frame, "5m", "1h", 0.8).iloc[0]["is_incomplete"]


def test_session_window_utc(cfg):
    s = Session(cfg["session"])
    t = pd.Series(
        pd.to_datetime(
            [
                "2026-10-05 11:55Z",
                "2026-10-05 12:00Z",
                "2026-10-05 20:55Z",
                "2026-10-05 21:00Z",
                "2026-10-03 14:00Z",
            ],
            utc=True,
        )
    )  # último é sábado
    assert s.in_session(t).tolist() == [False, True, True, False, False]
