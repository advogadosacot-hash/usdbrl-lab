from datetime import UTC, datetime, timedelta, timezone

import pytest

from usdbrl_lab.common.clock import ensure_utc, parse_iso_utc, to_iso_utc, utc_now
from usdbrl_lab.common.hashing import canonical_json, canonical_sha256, sha256_bytes, sha256_file


def test_utc_now_is_aware_utc():
    now = utc_now()
    assert now.tzinfo is UTC


def test_naive_datetime_is_rejected():
    with pytest.raises(ValueError, match="fuso"):
        ensure_utc(datetime(2026, 10, 5, 14, 15))  # noqa: DTZ001


def test_brasilia_converts_to_utc():
    brt = timezone(timedelta(hours=-3))
    assert ensure_utc(datetime(2026, 10, 5, 11, 15, tzinfo=brt)) == datetime(
        2026, 10, 5, 14, 15, tzinfo=UTC
    )


def test_iso_roundtrip():
    dt = parse_iso_utc("2026-10-05T14:15:00Z")
    assert to_iso_utc(dt) == "2026-10-05T14:15:00Z"
    assert parse_iso_utc("2026-10-05T11:15:00-03:00") == dt


def test_iso_without_offset_is_rejected():
    with pytest.raises(ValueError):
        parse_iso_utc("2026-10-05T14:15:00")


def test_canonical_hash_ignores_key_order():
    assert canonical_sha256({"a": 1, "b": [1, 2]}) == canonical_sha256({"b": [1, 2], "a": 1})
    assert canonical_json({"b": 1, "a": "ç"}) == '{"a":"ç","b":1}'


def test_sha256_known_value(tmp_path):
    expected = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    assert sha256_bytes(b"abc") == expected
    path = tmp_path / "x.bin"
    path.write_bytes(b"abc")
    assert sha256_file(path) == expected
