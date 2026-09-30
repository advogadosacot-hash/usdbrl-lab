"""Linha de comando do usdbrl-lab.

Fase 1: ``version``, ``config-check`` e ``ingest``. Os comandos de previsão, resolução,
treino e publicação entram nas fases correspondentes.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from usdbrl_lab import __version__
from usdbrl_lab.common.config import ConfigError, load_config


def _cmd_ingest(args: argparse.Namespace) -> int:
    from usdbrl_lab.ingest.run import run_ingest

    data_dir = Path(args.data_dir)
    if not data_dir.is_dir():
        print(f"ERRO: diretório de dados não existe: {data_dir}", file=sys.stderr)
        return 1
    summary = run_ingest(data_dir, backfill=args.backfill)
    # Só contagens e decisões: este texto aparece nos logs públicos do Actions.
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
    return 1 if summary["status"] == "failed" else 0


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
    ingest = sub.add_parser("ingest", help="coleta Yahoo + PTAX e grava no repositório de dados")
    ingest.add_argument("--data-dir", required=True, help="clone local do usdbrl-data")
    ingest.add_argument(
        "--backfill", action="store_true", help="coleta todo o histórico disponível"
    )
    ingest.set_defaults(func=_cmd_ingest)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
