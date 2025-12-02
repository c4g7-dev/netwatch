"""Application bootstrap helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from .config import AppConfig, load_config
from .db import init_db
from .exporter import CSVExporter
from .logging_setup import configure_logging
from .measurements.manager import MeasurementManager
from .scheduler import SchedulerService
from .web.app import create_web_app


class ApplicationContext:
    """Holds shared singletons for the service."""

    def __init__(self, config: AppConfig):
        self.config = config
        configure_logging(config)
        self.Session = init_db(config.paths.data_dir)
        self.measurements = MeasurementManager(config, self.Session)
        self.exporter = CSVExporter(config, self.Session)
        self.scheduler = SchedulerService(config, self.measurements, self.exporter)
        self.web_app = create_web_app(
            config=config,
            session_factory=self.Session,
            measurement_manager=self.measurements,
            exporter=self.exporter,
            scheduler=self.scheduler,
        )

    def start(self) -> None:
        self.scheduler.start()


def bootstrap(config_path: Optional[str] = None) -> ApplicationContext:
    """Load configuration and wire dependencies."""

    config_file = Path(config_path).resolve() if config_path else None
    config = load_config(str(config_file)) if config_file else load_config()
    return ApplicationContext(config)
