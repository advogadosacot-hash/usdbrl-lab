"""Carrega e valida a configuração versionada em config/*.toml (seções 22 e 29).

Regras:
- todos os arquivos esperados precisam existir e declarar ``schema_version``;
- nenhuma chave com cara de segredo é aceita (segredos só entram por variável de ambiente);
- ``config_sha`` é o SHA-256 do conteúdo normalizado, independente de formatação.
"""

from __future__ import annotations

import os
import re
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from usdbrl_lab.common.hashing import canonical_sha256

CONFIG_FILES: tuple[str, ...] = (
    "features",
    "gate",
    "models",
    "quality",
    "session",
    "sources",
    "targets",
)

CONFIG_DIR_ENV = "USDBRL_LAB_CONFIG_DIR"

_SECRET_KEY = re.compile(r"(secret|token|password|passwd|api[_-]?key|private[_-]?key)", re.I)


class ConfigError(ValueError):
    """Configuração ausente, malformada ou contendo segredo."""


@dataclass(frozen=True)
class Config:
    root: Path
    sections: Mapping[str, Mapping[str, Any]]
    sha: str

    def __getitem__(self, name: str) -> Mapping[str, Any]:
        return self.sections[name]


def default_config_dir() -> Path:
    override = os.environ.get(CONFIG_DIR_ENV)
    if override:
        return Path(override)
    # src/usdbrl_lab/common/config.py -> raiz do repositório
    return Path(__file__).resolve().parents[3] / "config"


def _find_secret_keys(node: Any, path: str = "") -> list[str]:
    found: list[str] = []
    if isinstance(node, Mapping):
        for key, value in node.items():
            here = f"{path}.{key}" if path else str(key)
            if _SECRET_KEY.search(str(key)):
                found.append(here)
            found.extend(_find_secret_keys(value, here))
    elif isinstance(node, list):
        for i, item in enumerate(node):
            found.extend(_find_secret_keys(item, f"{path}[{i}]"))
    return found


def load_config(config_dir: Path | None = None) -> Config:
    root = Path(config_dir) if config_dir is not None else default_config_dir()
    sections: dict[str, dict[str, Any]] = {}
    for name in CONFIG_FILES:
        path = root / f"{name}.toml"
        if not path.is_file():
            raise ConfigError(f"arquivo de configuração ausente: {path}")
        try:
            with path.open("rb") as fh:
                data = tomllib.load(fh)
        except tomllib.TOMLDecodeError as exc:
            raise ConfigError(f"TOML inválido em {path}: {exc}") from exc
        if not isinstance(data.get("schema_version"), int):
            raise ConfigError(f"{path} precisa declarar schema_version inteiro")
        secrets = _find_secret_keys(data)
        if secrets:
            raise ConfigError(
                f"{path} contém chaves com aparência de segredo: {', '.join(secrets)}; "
                "segredos só podem entrar por variável de ambiente"
            )
        sections[name] = data
    return Config(root=root, sections=sections, sha=canonical_sha256(sections))
