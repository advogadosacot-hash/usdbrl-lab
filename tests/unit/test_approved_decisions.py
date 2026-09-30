"""Trava das decisões aprovadas na Etapa 2 (seção 34, aprovadas em 2026-09-30).

Se um destes testes falhar, NÃO ajuste o teste para passar: a mudança exige nova
versão (target_v2 / gate_v2) e aprovação explícita do usuário.
"""

from statistics import NormalDist

import pytest

from usdbrl_lab.common.config import load_config

APPROVED_HORIZONS = ["5m", "15m", "1h", "4h", "24h"]


@pytest.fixture(scope="module")
def cfg():
    return load_config()


def test_p5_target_v1_frozen(cfg):
    t = cfg["targets"]["target_v1"]
    assert t["version"] == "target_v1"
    assert t["k"] == 0.4307
    assert t["sigma_estimator"] == "ewma"
    assert t["ewma_lambda"] == 0.94
    assert t["classes"] == ["up", "neutral", "down"]


def test_p5_k_is_the_theoretical_value(cfg):
    k_theory = NormalDist().inv_cdf(2 / 3)
    assert round(k_theory, 4) == cfg["targets"]["target_v1"]["k"]


def test_p5_garch_never_defines_target_v1(cfg):
    assert cfg["models"]["volatility"]["V2"]["affects_target"] is False
    assert "garch" not in cfg["targets"]["target_v1"]["sigma_estimator"]


def test_d4_horizons_exact(cfg):
    assert list(cfg["targets"]["target_v1"]["horizons"]) == APPROVED_HORIZONS
    assert list(cfg["session"]["emission_windows_local"]) == APPROVED_HORIZONS


def test_p3_emission_windows_and_24h_rule(cfg):
    windows = cfg["session"]["emission_windows_local"]
    assert windows == {
        "5m": ["09:00", "17:55"],
        "15m": ["09:00", "17:45"],
        "1h": ["09:00", "17:00"],
        "4h": ["09:00", "14:00"],
        "24h": ["09:00", "17:00"],
    }
    assert cfg["targets"]["target_v1"]["horizons"]["24h"]["end_rule"] == "same_time_next_session"


def test_p4_p6_price_fallback_chain(cfg):
    sources = cfg["sources"]
    assert sources["price_fallback_order"] == ["yahoo"]
    assert "binance" not in sources
    assert "binance" in sources["policy"]["excluded_v1"]
    assert "awesomeapi" not in sources
    assert "awesomeapi" in sources["policy"]["blocked_pending_terms"]


def test_d2_p1_yahoo_raw_never_public(cfg):
    yahoo = cfg["sources"]["yahoo"]
    assert yahoo["publish_raw"] is False
    assert yahoo["storage"] == "private"


def test_p7_gate_v1_frozen(cfg):
    g = cfg["gate"]["gate_v1"]
    assert g == {
        "version": "gate_v1",
        "primary_metric": "log_loss_skill_vs_B1",
        "G0_same_target_version": True,
        "G1_min_fraction_q_normal": 0.90,
        "G2_min_non_overlapping_walkforward": 300,
        "G4_dm_pvalue_vs_baselines": 0.05,
        "G4_shadow_skill_positive": True,
        "G5_dm_pvalue_vs_champion": 0.10,
        "G6_max_brier_worse_pct": 1.0,
        "G6_max_ece_worse": 0.01,
        "G7_min_fraction_positive_folds": 0.60,
        "G7_worst_fold_skill": -0.02,
        "G8_max_ece": 0.05,
        "G8_calibration_slope": [0.8, 1.2],
        "G9_coverage_80": [0.75, 0.85],
        "G10_holdout_skill_positive": True,
        "manual_promotion_allowed": False,
        "G3_shadow_sessions": {"5m": 10, "15m": 10, "1h": 10, "4h": 20, "24h": 40},
    }


def test_p7_demotion_confidence_and_blackout_frozen(cfg):
    gate = cfg["gate"]
    assert gate["demotion_v1"] == {"window_resolved": 300, "dm_pvalue": 0.10, "max_live_ece": 0.10}
    assert gate["confidence_v1"] == {
        "signal_strength_pp": [5, 15],
        "model_confidence_high_pvalue": 0.01,
        "model_confidence_medium_pvalue": 0.05,
        "js_disagreement": 0.1,
        "live_ece_downgrade": 0.05,
        "live_ece_suspend": 0.10,
        "live_window": 300,
        "min_effective_n": 30,
        "vol_regime_percentiles": [25, 75],
        "vol_regime_sessions": 250,
    }
    assert gate["event_blackout_v1"] == {"horizons": ["5m", "15m", "1h"], "extra_minutes": 15}


def test_quality_publish_threshold(cfg):
    score = cfg["quality"]["score"]
    assert score["publish_min"] == 0.70
    assert score["normal_min"] == 0.90
