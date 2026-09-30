"""Relógio do sistema: todo timestamp armazenado é UTC e com fuso explícito (seção 5)."""

from __future__ import annotations

from datetime import UTC, datetime


def utc_now() -> datetime:
    return datetime.now(UTC)


def ensure_utc(dt: datetime) -> datetime:
    """Converte um datetime com fuso para UTC. Datetime sem fuso é erro: nunca presumir."""
    if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
        raise ValueError("datetime sem fuso horário; informe o fuso explicitamente")
    return dt.astimezone(UTC)


def parse_iso_utc(value: str) -> datetime:
    """Lê ISO 8601 com fuso (aceita sufixo 'Z') e devolve em UTC."""
    return ensure_utc(datetime.fromisoformat(value.replace("Z", "+00:00")))


def to_iso_utc(dt: datetime) -> str:
    """Formato canônico de gravação: 2026-10-05T14:15:00Z."""
    return ensure_utc(dt).strftime("%Y-%m-%dT%H:%M:%SZ")
