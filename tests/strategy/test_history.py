"""Unit tests for strategy.history (SQLite snapshot store)."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

import pytest
from strategy.history import init_db, load_history, record_snapshot


@dataclass
class _FakeSnapshot:
    """Minimal stand-in for SubnetSnapshot — record_snapshot only reads three fields."""

    netuid: int
    alpha_price_tao: float
    fetched_at: float


def test_init_db_creates_schema(tmp_path: Path) -> None:
    db = tmp_path / "h.db"
    init_db(db)
    with sqlite3.connect(db) as conn:
        names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "snapshots" in names


def test_record_snapshot_round_trip(tmp_path: Path) -> None:
    db = tmp_path / "h.db"
    snaps = [
        _FakeSnapshot(netuid=1, alpha_price_tao=0.001, fetched_at=100.0),
        _FakeSnapshot(netuid=2, alpha_price_tao=0.002, fetched_at=100.0),
    ]
    inserted = record_snapshot(snaps, db)  # type: ignore[arg-type]
    assert inserted == 2
    h1 = load_history(1, db)
    assert len(h1) == 1
    assert h1[0].netuid == 1
    assert h1[0].alpha_price_tao == pytest.approx(0.001)
    assert h1[0].ts == pytest.approx(100.0)


def test_record_snapshot_idempotent_on_collision(tmp_path: Path) -> None:
    """Re-inserting same (netuid, ts) is a no-op (INSERT OR IGNORE)."""
    db = tmp_path / "h.db"
    snap = _FakeSnapshot(netuid=1, alpha_price_tao=0.001, fetched_at=100.0)
    record_snapshot([snap], db)  # type: ignore[arg-type]
    second = record_snapshot([snap], db)  # type: ignore[arg-type]
    assert second == 0
    assert len(load_history(1, db)) == 1


def test_load_history_returns_chronological_order(tmp_path: Path) -> None:
    db = tmp_path / "h.db"
    snaps = [
        _FakeSnapshot(netuid=1, alpha_price_tao=0.003, fetched_at=300.0),
        _FakeSnapshot(netuid=1, alpha_price_tao=0.001, fetched_at=100.0),
        _FakeSnapshot(netuid=1, alpha_price_tao=0.002, fetched_at=200.0),
    ]
    record_snapshot(snaps, db)  # type: ignore[arg-type]
    history = load_history(1, db)
    assert [p.ts for p in history] == [100.0, 200.0, 300.0]


def test_load_history_missing_db_returns_empty(tmp_path: Path) -> None:
    assert load_history(1, tmp_path / "does-not-exist.db") == []
