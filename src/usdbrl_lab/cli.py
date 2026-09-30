"""Linha de comando do usdbrl-lab.

Fase 0 expõe apenas ``version`` e ``config-check``. Os comandos de coleta, previsão,
resolução, treino e publicação entram nas fases correspondentes.
"""

from __future__ import annotations

import argparse
import sys

from usdbrl_lab import __version__
from usdbrl_lab.common.config import ConfigError, load_config


def _cmd_version(_: argparse.Namespace) -> int:
    print(__version__)
    return 0


def _cmd_config_check(_: argparse.Namespace) -> int:
    try:
        cfg = load_config()
    except ConfigError as exc:
        print(f"ERRO: {exc}", file=sys.stderr)
        return 1
    target = cfg["targets"]["target_v1"]
    gate = cfg["gate"]["gate_v1"]
    print(f"config_sha={cfg.sha}")
    print(f"target={target['version']} k={target['k']} sigma={target['sigma_estimator']}")
    print(f"gate={gate['version']}")
    print(f"price_fallback_order={cfg['sources']['price_fallback_order']}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="usdbrl-lab")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("version", help="mostra a versão").set_defaults(func=_cmd_version)
    sub.add_parser("config-check", help="valida config/*.toml e mostra o config_sha").set_defaults(
        func=_cmd_config_check
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
