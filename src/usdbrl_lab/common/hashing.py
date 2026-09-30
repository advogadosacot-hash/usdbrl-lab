"""Hashes estáveis para versionamento (seção 22 da especificação)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path, chunk_size: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json(obj: Any) -> str:
    """JSON determinístico: chaves ordenadas, sem espaços, UTF-8 preservado."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def canonical_sha256(obj: Any) -> str:
    """Hash do conteúdo, independente de formatação e ordem das chaves."""
    return sha256_bytes(canonical_json(obj).encode("utf-8"))
