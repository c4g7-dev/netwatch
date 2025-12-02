"""CSV export helpers for measurement data."""

from __future__ import annotations

import csv
import io
from datetime import datetime
from pathlib import Path
from typing import Optional

from .config import AppConfig
from .db import Measurement, get_session


class CSVExporter:
    def __init__(self, config: AppConfig, session_factory):
        self.config = config
        self.Session = session_factory

    def build_csv(self, start: Optional[datetime] = None, end: Optional[datetime] = None) -> io.StringIO:
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(self._header())

        for row in self._iter_rows(start, end):
            writer.writerow(row)

        buffer.seek(0)
        return buffer

    def _header(self) -> list:
        return [
            "timestamp",
            "type",
            "server",
            "ping_idle_ms",
            "jitter_ms",
            "download_mbps",
            "upload_mbps",
            "ping_during_download_ms",
            "ping_during_upload_ms",
            "download_latency_ms",
            "upload_latency_ms",
            "bytes_used",
        ]

    def _iter_rows(self, start: Optional[datetime], end: Optional[datetime]):
        with get_session(self.Session) as session:
            query = session.query(Measurement).order_by(Measurement.timestamp)
            if start:
                query = query.filter(Measurement.timestamp >= start)
            if end:
                query = query.filter(Measurement.timestamp <= end)
            for measurement in query.all():
                yield self._row_for_measurement(measurement)

    @staticmethod
    def _row_for_measurement(measurement: Measurement) -> list:
        cells = [
            measurement.ping_idle_ms,
            measurement.jitter_ms,
            measurement.download_mbps,
            measurement.upload_mbps,
            measurement.ping_during_download_ms,
            measurement.ping_during_upload_ms,
            measurement.download_latency_ms,
            measurement.upload_latency_ms,
            measurement.bytes_used,
        ]
        normalized = [CSVExporter._blank_if_none(value) for value in cells]
        return [
            measurement.timestamp.isoformat(),
            measurement.measurement_type,
            CSVExporter._blank_if_none(measurement.server),
            *normalized,
        ]

    @staticmethod
    def _blank_if_none(value):
        return "" if value is None else value

    def write_snapshot(self) -> Path:
        buffer = self.build_csv()
        target = self.config.paths.data_dir / self.config.export.csv_name
        target.write_text(buffer.getvalue(), encoding="utf-8")
        return target
