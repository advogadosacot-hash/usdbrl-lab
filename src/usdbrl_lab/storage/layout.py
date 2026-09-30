"""Caminhos do repositório de dados (seção 25)."""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path


def symbol_slug(symbol: str) -> str:
    """'BRL=X' -> 'brl_x' (caminhos seguros em qualquer sistema)."""
    return re.sub(r"[^a-z0-9]+", "_", symbol.lower()).strip("_")


def market_data_dir(root: Path, symbol: str, interval: str) -> Path:
    return root / "market_data" / symbol_slug(symbol) / interval


def market_data_file(root: Path, symbol: str, interval: str, day: date) -> Path:
    return market_data_dir(root, symbol, interval) / f"{day:%Y}" / f"{day:%m}" / f"{day:%d}.parquet"


def raw_payload_file(root: Path, source: str, day: date, run_id: str) -> Path:
    return root / "raw" / source / f"{day:%Y}" / f"{day:%m}" / f"{day:%d}" / f"{run_id}.json.gz"


def ops_file(root: Path, table: str, day: date) -> Path:
    return root / "ops" / table / f"{day:%Y}" / f"{day:%m}" / f"{day:%d}.jsonl"
