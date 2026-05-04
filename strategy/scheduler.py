# The MIT License (MIT)
# Copyright (c) 2026 lab-bittensor contributors

# Strategy scheduler — runs evaluation and economics tools on schedule.

import argparse
import logging
import os
import subprocess
import sys
from pathlib import Path

import schedule
import yaml

logger = logging.getLogger(__name__)


# Default schedule configuration
DEFAULT_SCHEDULE = {
    "evaluator_interval_hours": 6,
    "snapshot_time": "00:00",
    "economics_time": "01:00",
    "dry_run": False,
    "log_level": "INFO",
}

# Env var → config key mapping (env vars override YAML file or defaults)
_ENV_OVERRIDES = {
    "SCHEDULE_EVALUATOR_INTERVAL_HOURS": ("evaluator_interval_hours", int),
    "SCHEDULE_SNAPSHOT_TIME": ("snapshot_time", str),
    "SCHEDULE_ECONOMICS_TIME": ("economics_time", str),
    "SCHEDULE_DRY_RUN": ("dry_run", lambda v: v.lower() in ("true", "1", "yes")),
    "LOG_LEVEL": ("log_level", str),
}


def load_config(config_path: str) -> dict:
    """Load schedule configuration from YAML file.

    Args:
        config_path: Path to schedule.yaml file

    Returns:
        Configuration dict with defaults merged
    """
    config = DEFAULT_SCHEDULE.copy()

    config_file = Path(config_path)
    if config_file.exists():
        with open(config_file) as f:
            user_config = yaml.safe_load(f) or {}
        config.update(user_config)
        logger.info(f"Loaded config from {config_path}")
    else:
        logger.debug(f"Config file not found: {config_path}, checking env vars")

    # Env vars override YAML file and built-in defaults
    for env_key, (config_key, converter) in _ENV_OVERRIDES.items():
        if env_key in os.environ:
            config[config_key] = converter(os.environ[env_key])

    return config


def run_evaluator(network: str, dry_run: bool) -> None:
    """Run subnet evaluator."""
    logger.info("Running subnet evaluator...")
    cmd = [
        sys.executable, "-m", "strategy.subnet_evaluator",
        "--network", network,
    ]
    if dry_run:
        cmd.append("--dry-run")

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        logger.info(f"Evaluator completed:\n{result.stdout}")
    else:
        logger.error(f"Evaluator failed:\n{result.stderr}")


def run_snapshot(network: str, dry_run: bool) -> None:
    """Run alpha price snapshot."""
    logger.info("Running alpha snapshot...")
    cmd = [
        sys.executable, "-m", "strategy.alpha_snapshot",
        "--network", network,
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        logger.info(f"Snapshot completed:\n{result.stdout}")
    else:
        logger.error(f"Snapshot failed:\n{result.stderr}")


def run_economics(netuid: int, network: str, dry_run: bool) -> None:
    """Run alpha economics comparison."""
    logger.info(f"Running alpha economics for netuid {netuid}...")
    cmd = [
        sys.executable, "-m", "strategy.alpha_economics",
        "--netuid", str(netuid),
        "--network", network,
    ]
    if dry_run:
        cmd.append("--dry-run")

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        logger.info(f"Economics completed:\n{result.stdout}")
    else:
        logger.error(f"Economics failed:\n{result.stderr}")


def setup_scheduler(config: dict, network: str, netuid: int) -> None:
    """Configure scheduled jobs."""
    dry_run = config.get("dry_run", False)

    # Schedule evaluator every N hours
    evaluator_hours = config.get("evaluator_interval_hours", 6)
    schedule.every(evaluator_hours).hours.do(
        run_evaluator,
        network=network,
        dry_run=dry_run,
    )
    logger.info(f"Scheduled evaluator every {evaluator_hours} hours")

    # Schedule snapshot at specific time
    snapshot_time = config.get("snapshot_time", "00:00")
    schedule.every().day.at(snapshot_time).do(
        run_snapshot,
        network=network,
        dry_run=dry_run,
    )
    logger.info(f"Scheduled snapshot at {snapshot_time} daily")

    # Schedule economics at specific time
    economics_time = config.get("economics_time", "01:00")
    schedule.every().day.at(economics_time).do(
        run_economics,
        netuid=netuid,
        network=network,
        dry_run=dry_run,
    )
    logger.info(f"Scheduled economics at {economics_time} daily")


def main() -> None:
    """Main scheduler entry point."""
    parser = argparse.ArgumentParser(
        description="Schedule and run Bittensor strategy tools",
    )
    parser.add_argument(
        "--config",
        default="/config/schedule.yaml",
        help="Path to schedule configuration file (default: /config/schedule.yaml)",
    )
    parser.add_argument(
        "--network",
        choices=["finney", "test"],
        default="test",
        help="Bittensor network (default: test)",
    )
    parser.add_argument(
        "--netuid",
        type=int,
        default=None,
        help="Subnet netuid for economics tool (default: from config or prompt)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run all tools in dry-run mode (default: false)",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run all jobs once and exit (for testing)",
    )
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Log level (default: INFO)",
    )

    args = parser.parse_args()

    # Load configuration first so env vars (incl. LOG_LEVEL) are available
    config = load_config(args.config)

    # Determine effective log level: CLI arg > env var (via config) > default
    log_level_str = args.log_level if args.log_level != "INFO" else config.get("log_level", "INFO").upper()

    # Configure logging
    logging.basicConfig(
        level=getattr(logging, log_level_str),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    if args.dry_run:
        config["dry_run"] = True

    network = args.network
    netuid = args.netuid or config.get("netuid")
    if not netuid:
        logger.error("netuid required (set in config or via --netuid)")
        sys.exit(1)

    logger.info(f"Starting scheduler for network={network}, netuid={netuid}")
    if config.get("dry_run"):
        logger.info("DRY-RUN mode enabled — no chain interactions")

    # Setup scheduled jobs
    setup_scheduler(config, network, netuid)

    if args.once:
        # Run all jobs once and exit
        logger.info("Running jobs once (--once mode)")
        run_evaluator(network, config["dry_run"])
        run_snapshot(network, config["dry_run"])
        run_economics(netuid, network, config["dry_run"])
        return

    # Run scheduler loop
    logger.info("Scheduler started. Press Ctrl+C to exit.")
    try:
        while True:
            schedule.run_pending()
            import time
            time.sleep(60)
    except KeyboardInterrupt:
        logger.info("Scheduler stopped by user")


if __name__ == "__main__":
    main()
