"""Unit tests for strategy.verify_validator (offline, synthetic fixtures)."""

from __future__ import annotations

import json
from dataclasses import dataclass

import pytest
from strategy.verify_validator import (
    ValidatorStatus,
    fetch_validator_status,
    render_status,
    write_json,
)

# ---------------------------------------------------------------------------
# Fake bittensor objects — only the fields verify_validator reads
# ---------------------------------------------------------------------------

@dataclass
class _FakeAxon:
    ip: str = "1.2.3.4"
    port: int = 8091


class _FakeTensor(list):
    """list subclass whose items expose .item() (mimics a 1-D torch tensor slice)."""

    def __getitem__(self, idx):  # type: ignore[override]
        val = super().__getitem__(idx)
        return _TensorScalar(val)


@dataclass
class _TensorScalar:
    _v: float

    def item(self) -> float:
        return self._v

    def __float__(self) -> float:
        return self._v


def _metagraph(
    hotkeys: list[str],
    axons: list[_FakeAxon] | None = None,
    stakes: list[float] | None = None,
    incentives: list[float] | None = None,
    consensuses: list[float] | None = None,
    vtrusts: list[float] | None = None,
    permits: list[bool] | None = None,
    last_updates: list[int] | None = None,
):
    n = len(hotkeys)
    axons = axons or [_FakeAxon() for _ in range(n)]
    stakes = stakes or [0.0] * n
    incentives = incentives or [0.0] * n
    consensuses = consensuses or [0.0] * n
    vtrusts = vtrusts or [0.0] * n
    permits = permits or [False] * n
    last_updates = last_updates or [0] * n

    class _Meta:
        pass

    m = _Meta()
    m.hotkeys = hotkeys
    m.axons = axons
    m.S = _FakeTensor(stakes)
    m.I = _FakeTensor(incentives)   # bittensor v10: incentive (was R/rank)
    m.C = _FakeTensor(consensuses)  # bittensor v10: consensus (was T/trust)
    m.Tv = _FakeTensor(vtrusts)
    m.validator_permit = permits
    m.last_update = last_updates
    return m


class _FakeSubtensor:
    def __init__(self, metagraph, raise_on_metagraph: bool = False):
        self._metagraph = metagraph
        self._raise = raise_on_metagraph

    def metagraph(self, netuid):
        if self._raise:
            raise ConnectionError("chain unreachable")
        return self._metagraph


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

HOTKEY = "5GrwvaEF5zXb26Fz9rcQpDWS57CtERHpNehXCPcNoHGKutQY"


def test_not_registered_returns_none():
    meta = _metagraph(hotkeys=["5OtherHotkey"])
    subtensor = _FakeSubtensor(meta)
    result = fetch_validator_status(subtensor, HOTKEY, netuid=1, network="test")
    assert result is None


def test_registered_returns_status():
    axon = _FakeAxon(ip="10.0.0.1", port=8091)
    meta = _metagraph(
        hotkeys=[HOTKEY],
        axons=[axon],
        stakes=[500.0],
        incentives=[0.12345],
        consensuses=[0.99],
        vtrusts=[0.88],
        permits=[True],
        last_updates=[1234567],
    )
    subtensor = _FakeSubtensor(meta)
    status = fetch_validator_status(subtensor, HOTKEY, netuid=1, network="test")

    assert status is not None
    assert status.uid == 0
    assert status.axon_ip == "10.0.0.1"
    assert status.axon_port == 8091
    assert status.stake_tao == pytest.approx(500.0)
    assert status.incentive == pytest.approx(0.12345)
    assert status.consensus == pytest.approx(0.99)
    assert status.validator_trust == pytest.approx(0.88)
    assert status.validator_permit is True
    assert status.last_update_block == 1234567


def test_uid_resolves_correctly_for_multiple_hotkeys():
    other = "5FHneW46xGXgs5mUiveU4sbTyGBzmstUspZC92UhjJM694ty"
    meta = _metagraph(
        hotkeys=[other, HOTKEY],
        stakes=[100.0, 200.0],
    )
    subtensor = _FakeSubtensor(meta)
    status = fetch_validator_status(subtensor, HOTKEY, netuid=1, network="finney")
    assert status is not None
    assert status.uid == 1
    assert status.stake_tao == pytest.approx(200.0)


def test_connection_failure_raises_runtime_error():
    subtensor = _FakeSubtensor(None, raise_on_metagraph=True)
    with pytest.raises(RuntimeError, match="failed to fetch metagraph"):
        fetch_validator_status(subtensor, HOTKEY, netuid=1, network="test")


def test_render_status_no_crash(capsys):
    from rich.console import Console

    status = ValidatorStatus(
        hotkey=HOTKEY,
        netuid=1,
        network="test",
        uid=0,
        axon_ip="1.2.3.4",
        axon_port=8091,
        stake_tao=100.0,
        incentive=0.5,
        consensus=0.9,
        validator_trust=0.8,
        validator_permit=True,
        last_update_block=9999,
    )
    console = Console(file=open("/dev/null" if __import__("os").name != "nt" else "nul", "w"))
    render_status(status, console=console)  # must not raise


def test_write_json(tmp_path):
    status = ValidatorStatus(
        hotkey=HOTKEY,
        netuid=1,
        network="finney",
        uid=0,
        axon_ip="1.2.3.4",
        axon_port=8091,
        stake_tao=250.0,
        incentive=0.1,
        consensus=0.95,
        validator_trust=0.75,
        validator_permit=False,
        last_update_block=5000,
    )
    out = tmp_path / "status.json"
    write_json(status, out)
    data = json.loads(out.read_text())
    assert data["hotkey"] == HOTKEY
    assert data["uid"] == 0
    assert data["stake_tao"] == pytest.approx(250.0)
    assert data["registered"] is True


def test_main_not_registered(monkeypatch):
    """main() returns exit code 1 when hotkey not on subnet."""
    meta = _metagraph(hotkeys=["5OtherKey"])

    import strategy.verify_validator as vv

    monkeypatch.setattr(
        vv.bt if hasattr(vv, "bt") else __import__("bittensor"),  # type: ignore[attr-defined]
        "Subtensor",
        lambda **_: _FakeSubtensor(meta),
        raising=False,
    )

    # Patch at the module level so the import inside main() resolves correctly
    import sys
    import types

    fake_bt = types.SimpleNamespace(Subtensor=lambda network=None: _FakeSubtensor(meta))
    monkeypatch.setitem(sys.modules, "bittensor", fake_bt)

    from strategy.verify_validator import main

    rc = main(["--hotkey", "5OtherMissing", "--netuid", "1", "--network", "test"])
    assert rc == 1
