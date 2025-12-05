"""Speedtest measurement runners (Ookla CLI + speedtest-cli fallback)."""

from __future__ import annotations

import json
import logging
import platform
import re
import shutil
import subprocess
import tarfile
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

import requests

from ..config import AppConfig
from .models import MeasurementResult

LOGGER = logging.getLogger(__name__)


def _get_default_gateway() -> Optional[str]:
    """Get default gateway IP address."""
    try:
        if platform.system() == "Windows":
            result = subprocess.run(["route", "print", "0.0.0.0"], capture_output=True, text=True, timeout=5)
            # Look for default route
            for line in result.stdout.split('\n'):
                if '0.0.0.0' in line and '0.0.0.0' in line[:20]:
                    parts = line.split()
                    if len(parts) >= 3:
                        gateway = parts[2]
                        if re.match(r'\d+\.\d+\.\d+\.\d+', gateway):
                            return gateway
        else:
            # Linux/macOS
            result = subprocess.run(["ip", "route"], capture_output=True, text=True, timeout=5)
            for line in result.stdout.split('\n'):
                if 'default via' in line:
                    parts = line.split()
                    if len(parts) >= 3:
                        return parts[2]
    except Exception as e:
        LOGGER.debug(f"Failed to get default gateway: {e}")
    return None


def _ping_gateway(gateway_ip: str) -> Optional[float]:
    """Ping gateway once and return latency in ms."""
    try:
        if platform.system() == "Windows":
            cmd = ["ping", "-n", "1", "-w", "1000", gateway_ip]
        else:
            cmd = ["ping", "-c", "1", "-W", "1", gateway_ip]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=3)
        
        if result.returncode == 0:
            # Parse ping time
            if platform.system() == "Windows":
                match = re.search(r"time[=<](\d+(?:\.\d+)?)", result.stdout, re.IGNORECASE)
            else:
                match = re.search(r"time=(\d+(?:\.\d+)?)", result.stdout, re.IGNORECASE)
            
            if match:
                return float(match.group(1))
    except Exception as e:
        LOGGER.debug(f"Failed to ping gateway {gateway_ip}: {e}")
    return None


def _platform_binary_name(config: AppConfig) -> Path:
    suffix = ".exe" if platform.system().lower().startswith("win") else ""
    binary_name = config.ookla.binary_name
    if suffix and not binary_name.endswith(suffix):
        binary_name = f"{binary_name}{suffix}"
    return config.paths.bin_dir / binary_name


def get_ookla_binary_path(config: AppConfig) -> Path:
    """Expose the resolved Ookla CLI path for other modules."""
    return _platform_binary_name(config)


def ensure_ookla_binary(config: AppConfig) -> Path:
    binary_path = _platform_binary_name(config)
    if binary_path.exists():
        return binary_path

    if not config.ookla.auto_download:
        raise FileNotFoundError(
            f"Missing Ookla CLI binary at {binary_path}. Enable auto_download or install manually."
        )

    platform_key = config.ookla_platform_key
    LOGGER.info(f"Detected platform: {platform_key}")
    
    url = config.ookla.urls.get(platform_key)
    if not url:
        raise ValueError(
            f"No Ookla download URL configured for platform {platform_key}. "
            f"Supported platforms: {list(config.ookla.urls.keys())}"
        )

    temp_path = _download_ookla_artifact(url)
    try:
        _install_ookla_artifact(temp_path, url, config, binary_path)
    finally:
        if temp_path.exists():
            temp_path.unlink()

    binary_path.chmod(0o755)
    return binary_path


def _download_ookla_artifact(url: str) -> Path:
    LOGGER.info("Downloading Ookla CLI from %s", url)
    response = requests.get(url, timeout=120)
    response.raise_for_status()

    with tempfile.NamedTemporaryFile(delete=False) as temp_file:
        temp_file.write(response.content)
        return Path(temp_file.name)


def _install_ookla_artifact(temp_path: Path, url: str, config: AppConfig, destination: Path) -> None:
    if url.endswith(".exe"):
        shutil.move(str(temp_path), destination)
        return

    if url.endswith(".zip"):
        with zipfile.ZipFile(temp_path, "r") as archive:
            member = next((m for m in archive.namelist() if m.endswith("speedtest.exe")), None)
            if not member:
                raise RuntimeError("zip archive did not contain speedtest.exe binary")
            archive.extract(member, path=config.paths.bin_dir)
            extracted = config.paths.bin_dir / member
            if extracted != destination:
                shutil.move(extracted, destination)
        return

    if url.endswith(".tgz"):
        with tarfile.open(temp_path, "r:gz") as archive:
            member = next((m for m in archive.getmembers() if m.name.endswith("speedtest")), None)
            if not member:
                raise RuntimeError("tarball did not contain speedtest binary")
            archive.extract(member, path=config.paths.bin_dir)
            extracted = config.paths.bin_dir / member.name
            if extracted != destination:
                shutil.move(extracted, destination)
        return

    raise RuntimeError("Unknown Ookla download artifact")


def run_speedtest_test(config: AppConfig) -> MeasurementResult:
    try:
        binary_path = ensure_ookla_binary(config)
        return _run_ookla_cli(config, binary_path)
    except Exception as exc:  # pylint: disable=broad-except
        LOGGER.warning("Ookla CLI failed (%s). Falling back to speedtest-cli", exc)
        return _run_speedtest_cli(config)


def _run_ookla_cli(config: AppConfig, binary_path: Path) -> MeasurementResult:
    command = [str(binary_path), "--format=json", "--progress=no", "--accept-license", "--accept-gdpr"]
    if config.speedtest.server_id:
        command += ["--server-id", str(config.speedtest.server_id)]
    if config.speedtest.extra_args:
        command += list(config.speedtest.extra_args)

    completed = subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
    )
    data = json.loads(completed.stdout)
    return _convert_ookla_payload(data)


def _run_speedtest_cli(config: AppConfig) -> MeasurementResult:
    module = config.speedtest.fallback_module
    command = ["python", "-m", module, "--json"]
    completed = subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
    )
    data = json.loads(completed.stdout)
    return _convert_speedtest_cli_payload(data)


def _convert_ookla_payload(data: Dict) -> MeasurementResult:
    timestamp = _parse_timestamp(data.get("timestamp"))
    download = data.get("download", {})
    upload = data.get("upload", {})
    ping = data.get("ping", {})
    server = data.get("server", {})

    download_mbps = _bandwidth_to_mbps(download.get("bandwidth"))
    upload_mbps = _bandwidth_to_mbps(upload.get("bandwidth"))
    bytes_used = (download.get("bytes") or 0) + (upload.get("bytes") or 0)
    
    # Measure gateway ping
    gateway_ping = None
    gateway_ip = _get_default_gateway()
    if gateway_ip:
        gateway_ping = _ping_gateway(gateway_ip)
        LOGGER.debug(f"Gateway ping to {gateway_ip}: {gateway_ping}ms")

    return MeasurementResult(
        measurement_type="speedtest",
        timestamp=timestamp,
        server=server.get("name"),
        ping_idle_ms=ping.get("latency"),
        jitter_ms=ping.get("jitter"),
        download_mbps=download_mbps,
        upload_mbps=upload_mbps,
        ping_during_download_ms=_latency_value(download, "high"),
        ping_during_upload_ms=_latency_value(upload, "high"),
        download_latency_ms=_latency_value(download, "iqm"),
        upload_latency_ms=_latency_value(upload, "iqm"),
        gateway_ping_ms=gateway_ping,
        bytes_used=bytes_used,
        raw_json={"source": "ookla", "payload": data},
    )


def _convert_speedtest_cli_payload(data: Dict) -> MeasurementResult:
    download_mbps = (data.get("download") or 0) / 1_000_000
    upload_mbps = (data.get("upload") or 0) / 1_000_000
    bytes_used = (data.get("bytes_sent") or 0) + (data.get("bytes_received") or 0)

    timestamp = _parse_timestamp(data.get("timestamp"))
    server = data.get("server", {})
    
    # Measure gateway ping
    gateway_ping = None
    gateway_ip = _get_default_gateway()
    if gateway_ip:
        gateway_ping = _ping_gateway(gateway_ip)
        LOGGER.debug(f"Gateway ping to {gateway_ip}: {gateway_ping}ms")

    return MeasurementResult(
        measurement_type="speedtest-fallback",
        timestamp=timestamp,
        server=server.get("name"),
        ping_idle_ms=data.get("ping"),
        jitter_ms=None,
        download_mbps=download_mbps,
        upload_mbps=upload_mbps,
        ping_during_download_ms=None,
        ping_during_upload_ms=None,
        download_latency_ms=None,
        upload_latency_ms=None,
        gateway_ping_ms=gateway_ping,
        bytes_used=bytes_used,
        raw_json={"source": "speedtest-cli", "payload": data},
    )


def _bandwidth_to_mbps(value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    return (value * 8) / 1_000_000


def _latency_value(section: Dict, key: str) -> Optional[float]:
    latency = section.get("latency") or {}
    return latency.get(key)


def _parse_timestamp(raw: Optional[str]) -> datetime:
    if not raw:
        return datetime.utcnow()
    clean = raw.replace("Z", "+00:00") if raw.endswith("Z") else raw
    return datetime.fromisoformat(clean)
