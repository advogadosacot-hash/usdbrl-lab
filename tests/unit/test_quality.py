import pandas as pd
from synthetic import candles_frame, random_walk

from usdbrl_lab.normalize.session import Session
from usdbrl_lab.quality.checks import (
    FLAG_ANOMALY,
    FLAG_FROZEN,
    FLAG_IMPLAUSIBLE,
    apply_candle_rules,
)
from usdbrl_lab.quality.reconcile import yahoo_vs_ptax
from usdbrl_lab.quality.score import score_5m

LAM = 0.94


def _day(n=100, start="2026-10-05 12:00Z", seed=1):
    times = pd.date_range(start, periods=n, freq="5min")
    return candles_frame(times, random_walk(n, seed=seed))


def _rules(frame, cfg, interval="5m"):
    ins = Session(cfg["session"]).in_session(frame["event_time"])
    return apply_candle_rules(frame, ins, cfg["quality"], LAM, interval)


def test_implausible_price_rejected(cfg):
    f = _day(30)
    f.loc[5, ["open", "high", "low", "close"]] = 20.0  # fora de [2, 15]
    f.loc[6, "high"] = f.loc[6, "low"] - 0.01  # high < low
    out = _rules(f, cfg)
    assert out.loc[5, "quality_flag"] == FLAG_IMPLAUSIBLE and not out.loc[5, "is_valid"]
    assert out.loc[6, "quality_flag"] == FLAG_IMPLAUSIBLE


def test_anomaly_rejected_without_cascade(cfg):
    f = _day(60)
    jump = f.loc[40:, ["open", "high", "low", "close"]] * 1.03  # salto real de 3% que persiste
    f.loc[40:, ["open", "high", "low", "close"]] = jump
    out = _rules(f, cfg)
    assert out.loc[40, "quality_flag"] == FLAG_ANOMALY  # sem 2ª fonte: não confirmado
    assert out.loc[41:, "is_valid"].all()  # os seguintes não são contaminados


def test_overnight_gap_is_not_a_5min_return(cfg):
    a = _day(108, "2026-10-05 12:00Z", seed=2)
    b = _day(30, "2026-10-06 12:00Z", seed=3)
    b[["open", "high", "low", "close"]] *= 1.05  # abertura 5% acima do fechamento anterior
    out = _rules(pd.concat([a, b], ignore_index=True), cfg)
    assert (out["quality_flag"] != FLAG_ANOMALY).all()


def test_anomaly_rule_only_on_5m_grid(cfg):
    times = pd.date_range("2026-10-05 12:00Z", periods=40, freq="1h")
    f = candles_frame(times, random_walk(40, seed=4, sigma=0.0001))
    f.loc[30:, ["open", "high", "low", "close"]] *= 1.03
    out = _rules(f, cfg, interval="1h")
    assert (out["quality_flag"] != FLAG_ANOMALY).all()


def test_frozen_feed_flagged(cfg):
    f = _day(30)
    f.loc[10:16, ["open", "high", "low", "close"]] = 4.05  # 7 closes idênticos
    out = _rules(f, cfg)
    assert (out.loc[10:16, "quality_flag"] == FLAG_FROZEN).all()


def test_short_gap_imputed_long_gap_not(cfg):
    f = _day(40)
    f.loc[[10, 11], ["open", "high", "low", "close"]] = None  # 2 seguidos: imputa
    f.loc[[20, 21, 22], ["open", "high", "low", "close"]] = None  # 3 seguidos: não imputa
    f["is_valid"] = f["close"].notna()
    out = _rules(f, cfg)
    assert out.loc[[10, 11], "is_imputed"].all()
    assert (out.loc[[10, 11], "close"] == out.loc[9, "close"]).all()
    assert not out.loc[[20, 21, 22], "is_imputed"].any()
    assert not out.loc[[10, 11], "is_valid"].any()  # imputado não finge ser dado real


def test_gap_at_session_open_not_filled_from_previous_day(cfg):
    a = _day(108, "2026-10-05 12:00Z")
    b = _day(10, "2026-10-06 12:00Z")
    b.loc[0, ["open", "high", "low", "close"]] = None
    b["is_valid"] = b["close"].notna()
    out = _rules(pd.concat([a, b], ignore_index=True), cfg)
    assert not out.loc[108, "is_imputed"]


def test_rules_are_idempotent(cfg):
    f = _day(40)
    f.loc[[10, 11], ["open", "high", "low", "close"]] = None
    f["is_valid"] = f["close"].notna()
    once = _rules(f, cfg)
    twice = _rules(once, cfg)
    pd.testing.assert_frame_equal(once, twice)


def _score(frame, cfg, now, mode="normal", open_now=True):
    ins = Session(cfg["session"]).in_session(frame["event_time"])
    return score_5m(frame, ins, pd.Timestamp(now), open_now, mode, cfg["quality"])


def test_score_normal_and_consistency_unavailable(cfg):
    f = _rules(_day(24), cfg)  # 12:00–13:55
    s = _score(f, cfg, "2026-10-05 14:05Z")
    assert s.decision == "normal" and s.q == 1.0
    assert s.components["consistency"] is None


def test_score_stale_degrades_then_blocks(cfg):
    f = _rules(_day(24), cfg)  # último candle termina 14:00
    assert _score(f, cfg, "2026-10-05 14:20Z").decision == "degraded"  # 20 min > 15
    assert _score(f, cfg, "2026-10-05 14:31Z").decision == "blocked"  # > 30 min


def test_score_missing_block(cfg):
    f = _day(24)
    f.loc[[13, 15, 17, 19], ["open", "high", "low", "close"]] = None  # 4/12 > 25%
    f["is_valid"] = f["close"].notna()
    f = _rules(f, cfg)
    assert _score(f, cfg, "2026-10-05 14:05Z").decision == "blocked"


def test_score_source_failure_and_market_closed(cfg):
    f = _rules(_day(24), cfg)
    assert _score(f, cfg, "2026-10-05 14:05Z", mode=None).decision == "blocked"
    assert _score(f, cfg, "2026-10-05 23:00Z", open_now=False).decision == "market_closed"
    holiday = _score(f, cfg, "2026-10-06 14:05Z")  # dia útil sem nenhum candle válido
    assert holiday.decision == "market_closed"


def test_yahoo_vs_ptax_alert(cfg):
    f = _rules(_day(108), cfg)
    ins = Session(cfg["session"]).in_session(f["event_time"])
    close = float(f["close"].iloc[-1])
    ptax = pd.DataFrame(
        {
            "event_time": pd.to_datetime(["2026-10-05 16:03Z"]),
            "bulletin_type": ["Fechamento"],
            "bid": [close * 1.02],
            "ask": [close * 1.02],
        }
    )
    res = yahoo_vs_ptax(f, ins, ptax, "Fechamento", 1.5)
    assert res["compared_days"] == 1 and res["alert_days"] == ["2026-10-05"]
