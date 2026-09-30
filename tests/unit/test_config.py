import shutil

import pytest

from usdbrl_lab.common.config import CONFIG_FILES, ConfigError, default_config_dir, load_config


def _copy_config(tmp_path):
    dst = tmp_path / "config"
    shutil.copytree(default_config_dir(), dst)
    return dst


def test_loads_all_files():
    cfg = load_config()
    assert set(cfg.sections) == set(CONFIG_FILES)
    assert len(cfg.sha) == 64


def test_sha_ignores_formatting(tmp_path):
    base = load_config().sha
    cfg_dir = _copy_config(tmp_path)
    path = cfg_dir / "quality.toml"
    path.write_text("# comentário novo\n\n" + path.read_text(encoding="utf-8"), encoding="utf-8")
    assert load_config(cfg_dir).sha == base


def test_sha_changes_with_content(tmp_path):
    base = load_config().sha
    cfg_dir = _copy_config(tmp_path)
    path = cfg_dir / "quality.toml"
    text = path.read_text(encoding="utf-8").replace("block_minutes = 30", "block_minutes = 31")
    path.write_text(text, encoding="utf-8")
    assert load_config(cfg_dir).sha != base


def test_missing_file_is_error(tmp_path):
    cfg_dir = _copy_config(tmp_path)
    (cfg_dir / "gate.toml").unlink()
    with pytest.raises(ConfigError, match="ausente"):
        load_config(cfg_dir)


def test_schema_version_required(tmp_path):
    cfg_dir = _copy_config(tmp_path)
    path = cfg_dir / "session.toml"
    text = path.read_text(encoding="utf-8").replace("schema_version = 1", "")
    path.write_text(text, encoding="utf-8")
    with pytest.raises(ConfigError, match="schema_version"):
        load_config(cfg_dir)


@pytest.mark.parametrize("key", ["api_key", "token", "client_secret", "private_key", "password"])
def test_secret_like_keys_are_rejected(tmp_path, key):
    cfg_dir = _copy_config(tmp_path)
    path = cfg_dir / "sources.toml"
    path.write_text(
        path.read_text(encoding="utf-8") + f'\n[extra]\n{key} = "x"\n', encoding="utf-8"
    )
    with pytest.raises(ConfigError, match="segredo"):
        load_config(cfg_dir)


def test_env_override(tmp_path, monkeypatch):
    cfg_dir = _copy_config(tmp_path)
    monkeypatch.setenv("USDBRL_LAB_CONFIG_DIR", str(cfg_dir))
    assert load_config().root == cfg_dir
