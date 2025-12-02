"""Installer script to bootstrap the monitoring application."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from app.config import load_config
from app.measurements.speedtest_runner import ensure_ookla_binary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Install dependencies and download binaries")
    parser.add_argument("--config", default="config.yaml", help="Path to the config file")
    parser.add_argument("--venv", default=".venv", help="Virtual environment directory")
    parser.add_argument(
        "--requirements", default="requirements.txt", help="Requirements file to install"
    )
    return parser.parse_args()


def create_venv(venv_path: Path) -> Path:
    if not venv_path.exists():
        subprocess.check_call([sys.executable, "-m", "venv", str(venv_path)])
    python = venv_path / ("Scripts" if sys.platform.startswith("win") else "bin") / (
        "python.exe" if sys.platform.startswith("win") else "python"
    )
    return python


def install_requirements(python_bin: Path, requirements_file: Path) -> None:
    subprocess.check_call([str(python_bin), "-m", "pip", "install", "--upgrade", "pip"])
    subprocess.check_call([str(python_bin), "-m", "pip", "install", "-r", str(requirements_file)])


def main() -> None:
    args = parse_args()
    config = load_config(args.config)

    python_bin = create_venv(Path(args.venv))
    install_requirements(python_bin, Path(args.requirements))

    ensure_ookla_binary(config)
    print("Installation complete. Activate the virtual environment and run python main.py")


if __name__ == "__main__":
    main()
