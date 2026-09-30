"""Uma execução de coleta: Yahoo (1m, 5m, 1h) → validação → normalização → armazenamento,
mais a PTAX como referência oficial, registro de qualidade e registro da execução.

O resumo devolvido contém só contagens e decisões — nunca preços — porque é impresso
nos logs públicos do GitHub Actions (D2).
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from usdbrl_lab.common.clock import ensure_utc, to_iso_utc, utc_now
from usdbrl_lab.common.config import Config, load_config
from usdbrl_lab.ingest.fallback import fetch_with_fallback
from usdbrl_lab.ingest.retry import make_http_get
from usdbrl_lab.normalize.candles import canonical_candles
from usdbrl_lab.normalize.session import Session
from usdbrl_lab.quality.checks import FLAG_ANOMALY, FLAG_IMPLAUSIBLE, apply_candle_rules
from usdbrl_lab.quality.reconcile import native_vs_resampled_1h, yahoo_vs_ptax
from usdbrl_lab.quality.score import score_5m
from usdbrl_lab.sources import bcb, yahoo
from usdbrl_lab.sources.base import HttpGet, SourceError
from usdbrl_lab.storage.ops_io import append_jsonl, write_raw_payloads
from usdbrl_lab.storage.parquet_io import last_event_time, merge_rows, read_days, write_days

# Dias anteriores lidos só como contexto (EWMA, imputação); não são regravados.
CONTEXT_DAYS = {"1m": 0, "5m": 10, "1h": 30}
PTAX_VALUES = ["bid", "ask", "bulletin_type"]


@dataclass(frozen=True)
class Window:
    mode: str  # "period" | "range"
    start: datetime | None = None
    end: datetime | None = None
    chunk_days: int = 0
    range_: str = ""


def plan_window(
    root: Path, symbol: str, interval: str, now: datetime, backfill: bool, ycfg: dict[str, Any]
) -> Window:
    if backfill and interval == "1h":
        return Window("range", range_="730d")
    retention = timedelta(days=ycfg["retention_days"][interval])
    earliest = now - retention
    start = earliest
    if not backfill:
        last = last_event_time(root, symbol, interval)
        if last is not None:
            overlap = timedelta(hours=ycfg["incremental_overlap_hours"][interval])
            start = max(earliest, last.to_pydatetime() - overlap)
    return Window("period", start, now, ycfg["chunk_days"][interval])


def _run_id() -> str:
    gh = os.environ.get("GITHUB_RUN_ID")
    if gh:
        return f"{gh}-{os.environ.get('GITHUB_RUN_ATTEMPT', '1')}"
    return "local-" + utc_now().strftime("%Y%m%dT%H%M%SZ")


def run_ingest(
    data_dir: Path,
    *,
    backfill: bool = False,
    now: datetime | None = None,
    http_get: HttpGet | None = None,
    cfg: Config | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    started = time.monotonic()
    cfg = cfg or load_config()
    now = ensure_utc(now or utc_now())
    now_ts = pd.Timestamp(now)
    run_id = run_id or _run_id()
    root = Path(data_dir)
    scfg, qcfg = cfg["sources"], cfg["quality"]
    ycfg = scfg["yahoo"]
    session = Session(cfg["session"])
    lam = float(cfg["targets"]["target_v1"]["ewma_lambda"])
    http = scfg["http"]
    http_get = http_get or make_http_get(
        http["timeout_seconds"], http["retry_waits_seconds"], http["retry_on_status"]
    )
    ysrc = yahoo.YahooSource(http_get, ycfg["base_url"], ycfg["symbol"])
    symbol = ycfg["symbol"]
    chain = scfg["price_fallback_order"]

    summary: dict[str, Any] = {"run_id": run_id, "backfill": backfill, "intervals": {}}
    raw: dict[str, list] = {yahoo.SOURCE: [], bcb.SOURCE: []}
    frames: dict[str, pd.DataFrame] = {}
    fetched_from: dict[str, date] = {}
    attempts_all: dict[str, list] = {}

    for interval in ycfg["intervals"]:
        win = plan_window(root, symbol, interval, now, backfill, ycfg)

        def fetch(win=win, interval=interval):
            if win.mode == "range":
                return ysrc.fetch_range(interval, win.range_)
            return ysrc.fetch_period(interval, win.start, win.end, win.chunk_days)

        result, used, attempts = fetch_with_fallback(chain, {yahoo.SOURCE: fetch})
        attempts_all[interval] = attempts
        if result is None:
            summary["intervals"][interval] = {"status": "failed", "attempts": attempts}
            continue
        raw[yahoo.SOURCE].extend(result.responses)
        canon, n_open = canonical_candles(
            result.frame,
            symbol=symbol,
            interval=interval,
            source=used,
            run_id=run_id,
            now=now,
            ingested_at=utc_now(),
            backfill=backfill,
            close_grace_minutes=session.close_grace_minutes,
        )
        if canon.empty:
            summary["intervals"][interval] = {"status": "empty", "open_dropped": n_open}
            continue
        first_day = canon["event_time"].min().date()
        fetched_from[interval] = first_day
        context_start = first_day - timedelta(days=CONTEXT_DAYS[interval])
        existing = read_days(root, symbol, interval, start=context_start)
        merged, revised = merge_rows(existing, canon)
        in_sess = session.in_session(merged["event_time"]) if interval != "1m" else None
        merged = apply_candle_rules(merged, in_sess, qcfg, lam, interval)
        to_write = merged.loc[merged["event_time"].dt.date >= first_day]
        written = write_days(root, symbol, interval, to_write)
        frames[interval] = merged
        flags = to_write["quality_flag"].astype(str)
        summary["intervals"][interval] = {
            "status": "ok",
            "fetched_rows": int(len(result.frame)),
            "closed_rows": int(len(canon)),
            "open_dropped": n_open,
            "unaligned_dropped": result.dropped_unaligned,
            "valid_rows": int(to_write["is_valid"].sum()),
            "imputed_rows": int(to_write["is_imputed"].sum()),
            "rejected_rows": int(flags.isin([FLAG_IMPLAUSIBLE, FLAG_ANOMALY]).sum()),
            "revised_rows": revised,
            "files_written": len(written),
            "requests": len(result.responses),
        }

    # PTAX: referência oficial (não substitui candles intraday).
    pcfg = scfg["bcb"]["ptax"]
    psrc = bcb.PtaxSource(http_get, pcfg["base_url"], pcfg["currency"], pcfg["local_timezone"])
    today = now.date()
    if backfill:
        p_start = date.fromisoformat(pcfg["backfill_start"])
    else:
        p_start = today - timedelta(days=pcfg["incremental_lookback_days"])
    ptax_frames, ptax_status = [], "ok"
    cursor = p_start
    try:
        while cursor <= today:
            stop = min(date(cursor.year, 12, 31), today)
            res = psrc.fetch(cursor, stop)
            raw[bcb.SOURCE].extend(res.responses)
            ptax_frames.append(res.frame)
            cursor = stop + timedelta(days=1)
    except SourceError as exc:
        ptax_status = f"failed: {exc.kind} {exc}"
    ptax = pd.concat(ptax_frames, ignore_index=True) if ptax_frames else pd.DataFrame()
    ptax_written = 0
    if not ptax.empty:
        ptax = ptax.drop_duplicates("event_time").copy()
        ptax["symbol"], ptax["interval"], ptax["source"] = bcb.SYMBOL, bcb.INTERVAL, bcb.SOURCE
        ptax["available_time"] = ptax["event_time"]
        ptax["ingested_at"], ptax["run_id"] = pd.Timestamp(utc_now()), run_id
        existing = read_days(root, bcb.SYMBOL, bcb.INTERVAL, start=ptax["event_time"].min().date())
        merged_ptax, _ = merge_rows(existing, ptax, value_cols=PTAX_VALUES)
        ptax_written = len(write_days(root, bcb.SYMBOL, bcb.INTERVAL, merged_ptax))
        ptax = merged_ptax
    summary["ptax"] = {"status": ptax_status, "rows": int(len(ptax)), "files_written": ptax_written}

    # Qualidade (sobre a grade de 5 min) e conferências cruzadas.
    five = frames.get("5m", pd.DataFrame())
    if five.empty:
        quality = score_5m(
            five, pd.Series(dtype=bool), now_ts, session.is_open_at(now_ts), None, qcfg
        )
    else:
        ins5 = session.in_session(five["event_time"])
        quality = score_5m(five, ins5, now_ts, session.is_open_at(now_ts), "normal", qcfg)
    reconcile: dict[str, Any] = {}
    if not five.empty:
        recent5 = five.loc[five["event_time"].dt.date >= fetched_from.get("5m", today)]
        ins_recent = session.in_session(recent5["event_time"])
        if "1h" in frames:
            reconcile["native_vs_resampled_1h"] = native_vs_resampled_1h(
                recent5,
                frames["1h"],
                ins_recent,
                session.min_valid_fraction,
                float(qcfg["divergence"]["degrade_pct"]),
            )
        if not ptax.empty:
            reconcile["yahoo_vs_ptax"] = yahoo_vs_ptax(
                recent5,
                ins_recent,
                ptax,
                pcfg["closing_bulletin"],
                float(qcfg["divergence"]["ptax_alert_pct"]),
            )
    summary["quality"] = {"decision": quality.decision, "q": quality.q, "reasons": quality.reasons}
    summary["reconcile"] = reconcile

    # Registros privados: respostas brutas, qualidade e execução.
    for source, responses in raw.items():
        write_raw_payloads(root, source, today, run_id, responses)
    checked_at = to_iso_utc(now)
    append_jsonl(
        root,
        "data_quality",
        today,
        {
            "run_id": run_id,
            "checked_at": checked_at,
            "source_used": "yahoo" if frames else None,
            "attempts": attempts_all,
            **quality.to_dict(),
            "reconcile": reconcile,
        },
    )
    price_ok = "5m" in frames
    summary["status"] = (
        "ok" if price_ok and ptax_status == "ok" else ("partial" if price_ok else "failed")
    )
    append_jsonl(
        root,
        "runs",
        today,
        {
            "run_id": run_id,
            "workflow": os.environ.get("GITHUB_WORKFLOW", "local"),
            "trigger": os.environ.get("GITHUB_EVENT_NAME", "manual"),
            "code_sha": os.environ.get("GITHUB_SHA", "local"),
            "started_at": checked_at,
            "duration_s": round(time.monotonic() - started, 1),
            "backfill": backfill,
            "status": summary["status"],
            "intervals": summary["intervals"],
            "ptax": summary["ptax"],
        },
    )
    return summary
