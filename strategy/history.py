"""SQLite snapshot store for per-subnet Alpha→TAO price history.

Schema is `snapshots(netuid, alpha_price_tao, ts)` keyed on `(netuid, ts)` so a
re-run on the same instant is a no-op. Designed to be appended on every
`strategy.alpha_snapshot` invocation; `strategy.alpha_economics` reads back
chronologically-ordered series per netuid.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from strategy.data import SubnetSnapshot


_SCHEMA = """
CREATE TABLE IF NOT EXISTS snapshots (
    netuid          INTEGER NOT NULL,
    alpha_price_tao REAL    NOT NULL,
    ts              REAL    NOT NULL,
    PRIMARY KEY (netuid, ts)
);
CREATE INDEX IF NOT EXISTS idx_snapshots_netuid_ts ON snapshots(netuid, ts);
"""


@dataclass(frozen=True)
class PricePoint:
    """One price observation for a subnet at a moment in time."""

    netuid: int
    alpha_price_tao: float
    ts: float


def init_db(db_path: Path) -> None:
    """Ensure the SQLite file and schema exist at db_path. Idempotent."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.executescript(_SCHEMA)


def record_snapshot(snapshots: list["SubnetSnapshot"], db_path: Path) -> int:
    """Append one row per snapshot. Returns count actually inserted (collisions skipped)."""
    init_db(db_path)
    rows = [(s.netuid, s.alpha_price_tao, s.fetched_at) for s in snapshots]
    with sqlite3.connect(db_path) as conn:
        cur = conn.executemany(
            "INSERT OR IGNORE INTO snapshots (netuid, alpha_price_tao, ts) VALUES (?, ?, ?)",
            rows,
        )
        return cur.rowcount


def load_history(netuid: int, db_path: Path) -> list[PricePoint]:
    """Return all price points for a netuid, oldest first. Empty list if none."""
    if not db_path.exists():
        return []
    with sqlite3.connect(db_path) as conn:
        cur = conn.execute(
            "SELECT netuid, alpha_price_tao, ts FROM snapshots WHERE netuid = ? ORDER BY ts ASC",
            (netuid,),
        )
        return [PricePoint(netuid=r[0], alpha_price_tao=r[1], ts=r[2]) for r in cur.fetchall()]
