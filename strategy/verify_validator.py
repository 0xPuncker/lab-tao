"""On-chain validator verification CLI.

Connects to Bittensor, fetches metagraph for a subnet, and verifies that
a given hotkey is registered and actively participating.

Run with:
    python -m strategy.verify_validator --hotkey 5Grw... --netuid 1
    python -m strategy.verify_validator --hotkey 5Grw... --netuid 1 --network finney
    python -m strategy.verify_validator --hotkey 5Grw... --netuid 1 --json out.json
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from rich.console import Console
from rich.table import Table

if TYPE_CHECKING:
    import bittensor as bt

log = logging.getLogger("strategy.verify_validator")

TAOSWAP_EXPLORE = "https://taoswap.org/explore"
TAOSTATS_TESTNET = "https://x.taostats.io"


@dataclass
class ValidatorStatus:
    """On-chain status for one validator hotkey on a subnet.

    Field names match bittensor v10 metagraph tensor names:
    - incentive (meta.I) replaces the v9 rank (meta.R)
    - consensus (meta.C) replaces the v9 trust (meta.T)
    - validator_trust (meta.Tv) unchanged
    """

    hotkey: str
    netuid: int
    network: str
    uid: int
    axon_ip: str
    axon_port: int
    stake_tao: float
    incentive: float
    consensus: float
    validator_trust: float
    validator_permit: bool
    last_update_block: int
    registered: bool = True


def fetch_validator_status(
    subtensor: "bt.Subtensor",
    hotkey_ss58: str,
    netuid: int,
    network: str,
) -> ValidatorStatus | None:
    """Query metagraph and return ValidatorStatus, or None if not registered.

    Uses metagraph.hotkeys (list of ss58 strings) to locate the uid, then
    reads tensors/lists at that index for all metrics. Returns None when the
    hotkey is not in the metagraph (not registered).
    """
    try:
        metagraph = subtensor.metagraph(netuid)
    except Exception as exc:
        raise RuntimeError(f"failed to fetch metagraph for netuid {netuid}: {exc}") from exc

    try:
        uid = metagraph.hotkeys.index(hotkey_ss58)
    except ValueError:
        return None

    axon = metagraph.axons[uid]
    axon_ip = getattr(axon, "ip", "0.0.0.0")
    axon_port = getattr(axon, "port", 0)

    # Tensors expose .item() in PyTorch; fall back to float() for test fakes.
    def _f(val: object) -> float:
        return float(val.item() if hasattr(val, "item") else val)  # type: ignore[union-attr]

    def _get_tensor(obj: object, *attrs: str) -> object:
        """Return the first attribute that exists on obj (None if none found)."""
        for attr in attrs:
            val = getattr(obj, attr, None)
            if val is not None:
                return val
        return None

    # bittensor v10: I=incentive, C=consensus, Tv=validator_trust
    # bittensor v9:  R=rank,      T=trust,     Tv=validator_trust
    vtrust_raw = _get_tensor(metagraph, "Tv", "validator_trust")
    vtrust = _f(vtrust_raw[uid]) if vtrust_raw is not None else 0.0

    incentive_raw = _get_tensor(metagraph, "I", "R")
    consensus_raw = _get_tensor(metagraph, "C", "T")

    return ValidatorStatus(
        hotkey=hotkey_ss58,
        netuid=netuid,
        network=network,
        uid=uid,
        axon_ip=axon_ip,
        axon_port=axon_port,
        stake_tao=_f(metagraph.S[uid]),
        incentive=_f(incentive_raw[uid]) if incentive_raw is not None else 0.0,
        consensus=_f(consensus_raw[uid]) if consensus_raw is not None else 0.0,
        validator_trust=vtrust,
        validator_permit=bool(metagraph.validator_permit[uid]),
        last_update_block=int(metagraph.last_update[uid]),
    )


def render_status(status: ValidatorStatus, console: Console | None = None) -> None:
    """Print a rich table with the validator's on-chain metrics."""
    console = console or Console()

    table = Table(title=f"Validator status — netuid {status.netuid} ({status.network})")
    table.add_column("Field", style="bold")
    table.add_column("Value")

    permit_mark = "✓" if status.validator_permit else "✗"

    table.add_row("Hotkey", status.hotkey)
    table.add_row("UID", str(status.uid))
    table.add_row("Axon endpoint", f"{status.axon_ip}:{status.axon_port}")
    table.add_row("Stake (τ)", f"{status.stake_tao:.4f}")
    table.add_row("Incentive", f"{status.incentive:.6f}")
    table.add_row("Consensus", f"{status.consensus:.6f}")
    table.add_row("Validator trust", f"{status.validator_trust:.6f}")
    table.add_row("Validator permit", permit_mark)
    table.add_row("Last update (block)", str(status.last_update_block))

    console.print(table)
    is_testnet = status.network in ("test", "testnet")
    if is_testnet:
        console.print(f"\n[bold]taostats testnet explorer:[/bold] {TAOSTATS_TESTNET}/hotkey/{status.hotkey}")
        console.print(f"[bold]Subnet on testnet:[/bold]  {TAOSTATS_TESTNET}/subnet/{status.netuid}?network=test\n")
    else:
        console.print(f"\n[bold]taoswap.org explorer:[/bold] {TAOSWAP_EXPLORE}?netuid={status.netuid}")
        console.print(f"[bold]Hotkey to search:[/bold]  {status.hotkey}\n")


def write_json(status: ValidatorStatus, path: Path) -> None:
    path.write_text(json.dumps(asdict(status), indent=2))


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns 0 on success, 1 on failure."""
    parser = argparse.ArgumentParser(
        prog="strategy.verify_validator",
        description="Verify a Bittensor validator's on-chain registration and metrics.",
    )
    parser.add_argument("--hotkey", required=True, help="Hotkey ss58 address to verify.")
    parser.add_argument("--netuid", type=int, required=True, help="Subnet netuid to check.")
    parser.add_argument(
        "--network",
        default="finney",
        help="Bittensor network: 'finney' (mainnet, default), 'test', or chain endpoint URL.",
    )
    parser.add_argument(
        "--json",
        type=Path,
        default=None,
        dest="json_path",
        help="Also write structured JSON to this path.",
    )
    parser.add_argument(
        "--log-level",
        default="WARNING",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=args.log_level, format="%(levelname)s %(name)s: %(message)s")

    import bittensor as bt

    try:
        subtensor = bt.Subtensor(network=args.network)
    except Exception as exc:
        print(f"error: failed to connect to '{args.network}': {exc}", file=sys.stderr)
        return 1

    try:
        status = fetch_validator_status(subtensor, args.hotkey, args.netuid, args.network)
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if status is None:
        print(
            f"error: hotkey {args.hotkey} is NOT registered on netuid {args.netuid} "
            f"({args.network})",
            file=sys.stderr,
        )
        return 1

    render_status(status)

    if args.json_path:
        write_json(status, args.json_path)
        log.info("wrote JSON to %s", args.json_path)

    return 0


if __name__ == "__main__":
    sys.exit(main())
