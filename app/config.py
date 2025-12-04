"""Configuration loading helpers for the network performance monitor."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional
import platform
import yaml


@dataclass
class PathsConfig:
    data_dir: Path
    logs_dir: Path
    bin_dir: Path


@dataclass
class OoklaConfig:
    auto_download: bool = True
    binary_name: str = "speedtest"
    urls: Dict[str, str] = field(default_factory=dict)


@dataclass
class SpeedtestConfig:
    preferred: str = "ookla"
    fallback_module: str = "speedtest"
    server_id: Optional[str] = None
    extra_args: List[str] = field(default_factory=list)


@dataclass
class BufferbloatConfig:
    iperf_server: str = "iperf3.example.net"
    iperf_port: int = 5201
    download_duration: int = 15
    upload_duration: int = 15
    parallel_streams: int = 4
    ping_host: str = "1.1.1.1"
    ping_count: int = 20


@dataclass
class WebConfig:
    host: str = "0.0.0.0"
    port: int = 8000
    secret_key: str = "change-me"
    reverse_proxy_headers: bool = False


@dataclass
class ExportConfig:
    csv_name: str = "results.csv"


@dataclass
class LoggingConfig:
    level: str = "INFO"


@dataclass
class AppConfig:
    root_dir: Path
    paths: PathsConfig
    ookla: OoklaConfig
    speedtest: SpeedtestConfig
    bufferbloat: BufferbloatConfig
    web: WebConfig
    export: ExportConfig
    logging: LoggingConfig

    @property
    def ookla_platform_key(self) -> str:
        system = platform.system().lower()
        machine = platform.machine().lower()
        # Normalize machine architecture names
        if machine in ("amd64", "x86_64"):
            machine = "x86_64"
        elif machine in ("arm64", "aarch64"):
            machine = "aarch64"
        return f"{system}_{machine}"


def _as_path(base: Path, maybe_path: Optional[str]) -> Path:
    if not maybe_path:
        raise ValueError("Path configuration entries cannot be empty")
    path = (base / maybe_path).resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def load_config(path: Optional[str] = None) -> AppConfig:
    """Load application configuration from YAML file."""

    root_dir = Path(path).resolve().parent if path else Path.cwd()
    source_path = Path(path) if path else root_dir / "config.yaml"
    if not source_path.exists():
        raise FileNotFoundError(f"Missing configuration file at {source_path}")

    with source_path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}

    paths_data = data.get("paths", {})
    paths = PathsConfig(
        data_dir=_as_path(root_dir, paths_data.get("data_dir", "data")),
        logs_dir=_as_path(root_dir, paths_data.get("logs_dir", "logs")),
        bin_dir=_as_path(root_dir, paths_data.get("bin_dir", "bin")),
    )

    config = AppConfig(
        root_dir=root_dir,
        paths=paths,
        ookla=OoklaConfig(**data.get("ookla", {})),
        speedtest=SpeedtestConfig(**data.get("speedtest", {})),
        bufferbloat=BufferbloatConfig(**data.get("bufferbloat", {})),
        web=WebConfig(**data.get("web", {})),
        export=ExportConfig(**data.get("export", {})),
        logging=LoggingConfig(**data.get("logging", {})),
    )

    return config
