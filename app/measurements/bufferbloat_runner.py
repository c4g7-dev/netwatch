"""Bufferbloat measurements backed by iperf3 and ping."""

from __future__ import annotations

import json
import logging
import platform
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Optional, Tuple

from ..config import AppConfig
from .models import MeasurementResult

LOGGER = logging.getLogger(__name__)

PING_FLAG = "-n" if platform.system().lower().startswith("win") else "-c"


@dataclass
class IperfOutcome:
    mbps: Optional[float]
    bytes_transferred: Optional[int]
    raw_json: Dict


@dataclass
class PingStats:
    avg_ms: Optional[float]
    min_ms: Optional[float]
    max_ms: Optional[float]
    jitter_ms: Optional[float]
    raw_output: str


def run_bufferbloat_test(config: AppConfig) -> MeasurementResult:
    if not shutil.which("iperf3"):
        raise FileNotFoundError("iperf3 binary is required for bufferbloat tests")

    baseline_ping = _run_ping(config.bufferbloat.ping_host, config.bufferbloat.ping_count)
    download_result, download_ping = _run_iperf_with_ping(config, reverse=True)
    upload_result, upload_ping = _run_iperf_with_ping(config, reverse=False)

    total_bytes = (download_result.bytes_transferred or 0) + (upload_result.bytes_transferred or 0)

    raw_payload = {
        "baseline_ping": baseline_ping.raw_output,
        "download_ping": download_ping.raw_output,
        "upload_ping": upload_ping.raw_output,
        "download_iperf": download_result.raw_json,
        "upload_iperf": upload_result.raw_json,
    }

    return MeasurementResult(
        measurement_type="bufferbloat",
        timestamp=datetime.utcnow(),
        server=config.bufferbloat.iperf_server,
        ping_idle_ms=baseline_ping.avg_ms,
        jitter_ms=baseline_ping.jitter_ms,
        download_mbps=download_result.mbps,
        upload_mbps=upload_result.mbps,
        ping_during_download_ms=download_ping.avg_ms,
        ping_during_upload_ms=upload_ping.avg_ms,
        download_latency_ms=download_ping.max_ms,
        upload_latency_ms=upload_ping.max_ms,
        bytes_used=total_bytes,
        raw_json=raw_payload,
    )


def _run_iperf_with_ping(config: AppConfig, reverse: bool) -> Tuple[IperfOutcome, PingStats]:
    cmd = [
        "iperf3",
        "--json",
        "-c",
        config.bufferbloat.iperf_server,
        "-p",
        str(config.bufferbloat.iperf_port),
        "-t",
        str(config.bufferbloat.download_duration if reverse else config.bufferbloat.upload_duration),
        "-P",
        str(config.bufferbloat.parallel_streams),
    ]
    if reverse:
        cmd.append("-R")

    LOGGER.info("Running iperf3 command: %s", " ".join(cmd))
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    ping_stats = _run_ping(config.bufferbloat.ping_host, config.bufferbloat.ping_count)
    stdout, stderr = process.communicate()
    if process.returncode != 0:
        raise RuntimeError(f"iperf3 failed: {stderr}")

    payload = json.loads(stdout)
    outcome = _parse_iperf_payload(payload, reverse)
    return outcome, ping_stats


def _parse_iperf_payload(payload: Dict, reverse: bool) -> IperfOutcome:
    end_section = payload.get("end", {})
    summary_key = "sum_received" if reverse else "sum_sent"
    summary = end_section.get(summary_key) or end_section.get("sum", {})
    bits_per_second = summary.get("bits_per_second")
    mbps = (bits_per_second / 1_000_000) if bits_per_second else None
    return IperfOutcome(
        mbps=mbps,
        bytes_transferred=summary.get("bytes"),
        raw_json=payload,
    )


def _run_ping(host: str, count: int) -> PingStats:
    cmd = ["ping", PING_FLAG, str(count), host]
    completed = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        LOGGER.warning("Ping command failed: %s", completed.stderr)
    return _parse_ping_output(completed.stdout or "")


def _parse_ping_output(output: str) -> PingStats:
    avg = _extract_between(output, "Average = ", "ms")
    if avg is not None:
        # Windows flavor
        min_ms = _extract_between(output, "Minimum = ", "ms")
        max_ms = _extract_between(output, "Maximum = ", "ms")
        return PingStats(
            avg_ms=avg,
            min_ms=min_ms,
            max_ms=max_ms,
            jitter_ms=None,
            raw_output=output,
        )

    # Linux/mac flavor
    marker = "rtt min/avg/max/mdev ="
    if marker in output:
        stats_part = output.split(marker)[1].strip()
        values = stats_part.split("/")
        if len(values) >= 4:
            min_ms, avg_ms, max_ms, mdev = map(lambda v: float(v.split()[0]), values[:4])
            return PingStats(
                avg_ms=avg_ms,
                min_ms=min_ms,
                max_ms=max_ms,
                jitter_ms=mdev,
                raw_output=output,
            )

    return PingStats(avg_ms=None, min_ms=None, max_ms=None, jitter_ms=None, raw_output=output)


def _extract_between(text: str, prefix: str, suffix: str) -> Optional[float]:
    if prefix not in text:
        return None
    try:
        segment = text.split(prefix)[1]
        value_text = segment.split(suffix)[0]
        numeric = ''.join(ch for ch in value_text if (ch.isdigit() or ch == '.'))
        return float(numeric) if numeric else None
    except (IndexError, ValueError):
        return None
