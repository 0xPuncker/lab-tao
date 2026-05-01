"""Unit tests for strategy.alpha_economics CLI (offline, seeded SQLite)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pytest
from strategy.alpha_economics import main as cli_main
from strategy.history import record_snapshot


@dataclass
class _FakeSnapshot:
    netuid: int
    alpha_price_tao: float
    fetched_at: float


def _seed(db: Path, netuid: int, prices: list[float]) -> None:
    snaps = [_FakeSnapshot(netuid=netuid, alpha_price_tao=p, fetched_at=float(i)) for i, p in enumerate(prices)]
    record_snapshot(snaps, db)  # type: ignore[arg-type]


def test_cli_success_with_seeded_history(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    db = tmp_path / "h.db"
    _seed(db, netuid=7, prices=[0.001, 0.002, 0.003])
    exit_code = cli_main(["--netuid", "7", "--db", str(db)])
    captured = capsys.readouterr()
    assert exit_code == 0, captured.err
    # Table headers
    assert "strategy" in captured.out
    assert "tao realized" in captured.out
    # Title line names the netuid + point count
    assert "netuid 7" in captured.out
    assert "3 price points" in captured.out
    # Short strategy names survive rich.table truncation; full names checked via JSON in
    # test_cli_writes_json_when_requested.
    assert "hold_forever" in captured.out
    assert "dca_weekly" in captured.out


def test_cli_missing_history_exits_one(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    db = tmp_path / "empty.db"
    exit_code = cli_main(["--netuid", "999", "--db", str(db)])
    captured = capsys.readouterr()
    assert exit_code == 1
    assert "no history for netuid 999" in captured.err


def test_cli_writes_json_when_requested(tmp_path: Path) -> None:
    db = tmp_path / "h.db"
    out = tmp_path / "results.json"
    _seed(db, netuid=3, prices=[1.0, 1.5, 2.0])
    exit_code = cli_main(["--netuid", "3", "--db", str(db), "--json", str(out), "--alpha-per-epoch", "2.0"])
    assert exit_code == 0
    payload = json.loads(out.read_text())
    assert payload["netuid"] == 3
    assert payload["n_points"] == 3
    assert payload["alpha_per_epoch"] == 2.0
    assert len(payload["results"]) == 3
    names = {r["name"] for r in payload["results"]}
    assert names == {"convert_immediately", "hold_forever", "dca_weekly"}
