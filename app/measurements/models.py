"""Shared dataclasses for measurements."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Optional


@dataclass
class MeasurementResult:
    measurement_type: str
    timestamp: datetime
    server: Optional[str]
    ping_idle_ms: Optional[float]
    jitter_ms: Optional[float]
    download_mbps: Optional[float]
    upload_mbps: Optional[float]
    ping_during_download_ms: Optional[float]
    ping_during_upload_ms: Optional[float]
    download_latency_ms: Optional[float]
    upload_latency_ms: Optional[float]
    gateway_ping_ms: Optional[float]
    bytes_used: Optional[int]
    raw_json: Dict[str, Any]
