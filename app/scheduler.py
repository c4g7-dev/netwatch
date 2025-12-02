"""Background scheduler orchestration."""

from __future__ import annotations

import logging
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from .config import AppConfig
from .exporter import CSVExporter
from .measurements.manager import MeasurementManager

LOGGER = logging.getLogger(__name__)


class SchedulerService:
    def __init__(
        self,
        config: AppConfig,
        measurement_manager: MeasurementManager,
        exporter: CSVExporter,
    ) -> None:
        self.config = config
        self.measurements = measurement_manager
        self.exporter = exporter
        self.scheduler = BackgroundScheduler(timezone="UTC")
        self.started = False

    def start(self) -> None:
        if self.started or not self.config.scheduler.enabled:
            return
        trigger = IntervalTrigger(minutes=self.config.scheduler.interval_minutes)
        self.scheduler.add_job(self._run_cycle, trigger=trigger, id="scheduled-measurements")
        self.scheduler.start()
        self.started = True
        LOGGER.info(
            "Scheduler started with interval %s minutes", self.config.scheduler.interval_minutes
        )

    def shutdown(self) -> None:
        if self.started:
            self.scheduler.shutdown(wait=False)
            self.started = False

    def _run_cycle(self) -> None:
        LOGGER.info("Starting scheduled measurement cycle at %s", datetime.utcnow().isoformat())
        try:
            self.measurements.run_speedtest()
            self.measurements.run_bufferbloat()
            self.exporter.write_snapshot()
        except Exception as exc:  # pylint: disable=broad-except
            LOGGER.exception("Scheduled measurement failed: %s", exc)
