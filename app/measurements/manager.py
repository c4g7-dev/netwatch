"""Measurement orchestration and persistence layer."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import List, Optional

from sqlalchemy import desc
from sqlalchemy.orm import sessionmaker

from ..config import AppConfig
from ..db import Measurement, get_session
from .bufferbloat_runner import run_bufferbloat_test
from .models import MeasurementResult
from .speedtest_runner import ensure_ookla_binary, run_speedtest_test

LOGGER = logging.getLogger(__name__)


class MeasurementManager:
    def __init__(self, config: AppConfig, session_factory: sessionmaker):
        self.config = config
        self.Session = session_factory

    def _persist(self, result: MeasurementResult) -> Measurement:
        with get_session(self.Session) as session:
            record = Measurement(
                timestamp=result.timestamp,
                measurement_type=result.measurement_type,
                server=result.server,
                ping_idle_ms=result.ping_idle_ms,
                jitter_ms=result.jitter_ms,
                download_mbps=result.download_mbps,
                upload_mbps=result.upload_mbps,
                ping_during_download_ms=result.ping_during_download_ms,
                ping_during_upload_ms=result.ping_during_upload_ms,
                download_latency_ms=result.download_latency_ms,
                upload_latency_ms=result.upload_latency_ms,
                bytes_used=result.bytes_used,
                raw_json=json.dumps(result.raw_json),
            )
            session.add(record)
            session.flush()
            LOGGER.info(
                "Stored %s measurement at %s (down %.2f Mbps / up %.2f Mbps)",
                result.measurement_type,
                result.timestamp.isoformat(),
                result.download_mbps or 0,
                result.upload_mbps or 0,
            )
            return record

    def run_speedtest(self) -> Measurement:
        ensure_ookla_binary(self.config)
        result = run_speedtest_test(self.config)
        return self._persist(result)

    def run_bufferbloat(self) -> Optional[Measurement]:
        result = run_bufferbloat_test(self.config)
        if result is None:
            LOGGER.info("Bufferbloat test skipped (iperf3 not available)")
            return None
        return self._persist(result)

    def get_measurements(
        self,
        limit: Optional[int] = None,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        measurement_type: Optional[str] = None,
    ) -> List[Measurement]:
        with get_session(self.Session) as session:
            query = session.query(Measurement).order_by(desc(Measurement.timestamp))
            if measurement_type:
                query = query.filter(Measurement.measurement_type == measurement_type)
            if start:
                query = query.filter(Measurement.timestamp >= start)
            if end:
                query = query.filter(Measurement.timestamp <= end)
            if limit:
                query = query.limit(limit)
            rows = query.all()
            return list(reversed(rows))

    def latest_two(self) -> List[Measurement]:
        with get_session(self.Session) as session:
            rows = (
                session.query(Measurement)
                .order_by(desc(Measurement.timestamp))
                .limit(2)
                .all()
            )
            return rows

    def to_dict(self, measurement: Measurement) -> dict:
        return {
            "id": measurement.id,
            "timestamp": measurement.timestamp.isoformat(),
            "measurement_type": measurement.measurement_type,
            "server": measurement.server,
            "ping_idle": measurement.ping_idle_ms,
            "jitter": measurement.jitter_ms,
            "download": measurement.download_mbps,
            "upload": measurement.upload_mbps,
            "ping_under_download": measurement.ping_during_download_ms,
            "ping_under_upload": measurement.ping_during_upload_ms,
            "download_latency": measurement.download_latency_ms,
            "upload_latency": measurement.upload_latency_ms,
            "bytes_used": measurement.bytes_used,
        }
