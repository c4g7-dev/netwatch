"""Atomic updater for the Ookla CLI binary."""

from __future__ import annotations

import argparse
import shutil

from app.config import load_config
from app.measurements.speedtest_runner import ensure_ookla_binary, get_ookla_binary_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Update Ookla CLI binaries")
    parser.add_argument("--config", default="config.yaml", help="Path to configuration file")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = load_config(args.config)
    binary_path = get_ookla_binary_path(config)
    backup_path = binary_path.with_suffix(binary_path.suffix + ".bak")

    if binary_path.exists():
        shutil.copy2(binary_path, backup_path)
        binary_path.unlink()

    try:
        ensure_ookla_binary(config)
    except Exception:  # pylint: disable=broad-except
        if backup_path.exists():
            shutil.move(backup_path, binary_path)
        raise
    else:
        if backup_path.exists():
            backup_path.unlink()
        print("Ookla CLI updated successfully")


if __name__ == "__main__":
    main()
