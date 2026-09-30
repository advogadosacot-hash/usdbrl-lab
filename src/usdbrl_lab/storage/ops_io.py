"""Registros operacionais (ops/runs, ops/data_quality) em JSONL e respostas brutas em .json.gz."""

from __future__ import annotations

import gzip
import json
from datetime import date
from pathlib import Path
from typing import Any

from usdbrl_lab.common.clock import to_iso_utc
from usdbrl_lab.sources.base import HttpResponse
from usdbrl_lab.storage.layout import ops_file, raw_payload_file


def append_jsonl(root: Path, table: str, day: date, record: dict[str, Any]) -> Path:
    path = ops_file(root, table, day)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(record, ensure_ascii=False, sort_keys=True, default=str) + "\n")
    return path


def write_raw_payloads(
    root: Path, source: str, day: date, run_id: str, responses: list[HttpResponse]
) -> Path | None:
    if not responses:
        return None
    records = []
    for r in responses:
        try:
            body: Any = json.loads(r.body)
        except ValueError:
            body = r.body.decode("utf-8", errors="replace")
        records.append(
            {
                "url": r.url,
                "params": r.params,
                "status": r.status,
                "latency_s": r.latency_s,
                "fetched_at": to_iso_utc(r.fetched_at),
                "body": body,
            }
        )
    path = raw_payload_file(root, source, day, run_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(records, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    with gzip.GzipFile(path, "wb", mtime=0) as fh:
        fh.write(payload)
    return path
