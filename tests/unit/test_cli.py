from usdbrl_lab import __version__
from usdbrl_lab.cli import main


def test_version(capsys):
    assert main(["version"]) == 0
    assert capsys.readouterr().out.strip() == __version__


def test_config_check(capsys):
    assert main(["config-check"]) == 0
    out = capsys.readouterr().out
    assert "config_sha=" in out
    assert "target=target_v1 k=0.4307 sigma=ewma" in out
    assert "price_fallback_order=['yahoo']" in out


def test_config_check_reports_error(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("USDBRL_LAB_CONFIG_DIR", str(tmp_path))
    assert main(["config-check"]) == 1
    assert "ERRO" in capsys.readouterr().err
