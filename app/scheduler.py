"""Background scheduler orchestration."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger

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
        self.config_file = Path("data/scheduler_config.json")

    def _load_scheduler_config(self) -> dict:
        """Load scheduler configuration from JSON file."""
        if not self.config_file.exists():
            LOGGER.debug("Scheduler config file not found at %s, using defaults", self.config_file)
            return {
                "mode": "simple",
                "enabled": self.config.scheduler.enabled,
                "interval": self.config.scheduler.interval_minutes
            }
        
        try:
            with open(self.config_file, "r") as f:
                config = json.load(f)
                LOGGER.debug("Loaded scheduler config from %s: mode=%s", 
                           self.config_file, config.get("mode", "simple"))
                return config
        except PermissionError as exc:
            LOGGER.error("Permission denied reading scheduler config from %s: %s", 
                        self.config_file, exc)
            LOGGER.error("Using default configuration. Check file permissions.")
            return {
                "mode": "simple",
                "enabled": self.config.scheduler.enabled,
                "interval": self.config.scheduler.interval_minutes
            }
        except Exception as exc:
            LOGGER.error("Failed to load scheduler config from %s: %s", 
                        self.config_file, exc, exc_info=True)
            return {
                "mode": "simple",
                "enabled": self.config.scheduler.enabled,
                "interval": self.config.scheduler.interval_minutes
            }

    def _should_run_now(self, sched_config: dict) -> bool:
        """Check if we should run measurements based on current time and config."""
        now = datetime.now()
        current_day = now.strftime("%A").lower()
        current_time = now.strftime("%H:%M")
        
        mode = sched_config.get("mode", "simple")
        
        if mode == "simple":
            return sched_config.get("enabled", True)
        
        elif mode == "weekly":
            # Check if current day is in selected days (0=Sunday, 1=Monday, etc.)
            day_map = {0: "sunday", 1: "monday", 2: "tuesday", 3: "wednesday", 
                       4: "thursday", 5: "friday", 6: "saturday"}
            selected_days = sched_config.get("days", [1, 2, 3, 4, 5])
            
            # Convert current weekday (Monday=0) to match our format (Sunday=0)
            current_weekday = (now.weekday() + 1) % 7
            
            if current_weekday not in selected_days:
                return False
            
            # Check time window
            start_time = sched_config.get("startTime", "00:00")
            end_time = sched_config.get("endTime", "23:59")
            
            return start_time <= current_time <= end_time
        
        elif mode == "advanced":
            schedule = sched_config.get("schedule", {})
            
            if current_day not in schedule:
                return False
            
            # Check if current time falls within any of the day's time slots
            slots = schedule[current_day]
            for slot in slots:
                start_time = slot.get("startTime", "00:00")
                end_time = slot.get("endTime", "23:59")
                
                # Handle overnight slots (e.g., 22:00 to 02:00)
                if start_time > end_time:
                    # Overnight slot
                    if current_time >= start_time or current_time <= end_time:
                        return True
                else:
                    if start_time <= current_time <= end_time:
                        return True
            
            return False
        
        return True

    def _get_interval_minutes(self, sched_config: dict) -> int:
        """Get the interval in minutes based on config."""
        mode = sched_config.get("mode", "simple")
        
        if mode == "simple":
            return sched_config.get("interval", self.config.scheduler.interval_minutes)
        elif mode == "weekly":
            return sched_config.get("interval", 30)
        elif mode == "advanced":
            # For advanced mode, use the minimum interval from all active slots
            schedule = sched_config.get("schedule", {})
            intervals = []
            for day_slots in schedule.values():
                for slot in day_slots:
                    intervals.append(slot.get("interval", 30))
            return min(intervals) if intervals else 30
        
        return self.config.scheduler.interval_minutes

    def start(self) -> None:
        if self.started:
            LOGGER.warning("Scheduler already started, ignoring duplicate start request")
            return
        
        LOGGER.info("Initializing scheduler...")
        sched_config = self._load_scheduler_config()
        
        # Check if scheduler is enabled (for simple mode)
        if sched_config.get("mode") == "simple" and not sched_config.get("enabled", True):
            LOGGER.warning("Scheduler is disabled in configuration (simple mode)")
            LOGGER.info("To enable scheduler, go to the dashboard and toggle the scheduler on")
            return
        
        try:
            interval = self._get_interval_minutes(sched_config)
            trigger = IntervalTrigger(minutes=interval)
            self.scheduler.add_job(self._run_cycle, trigger=trigger, id="scheduled-measurements")
            self.scheduler.start()
            self.started = True
            LOGGER.info(
                "✓ Scheduler started successfully with interval %s minutes (mode: %s)", 
                interval, 
                sched_config.get("mode", "simple")
            )
        except Exception as exc:
            LOGGER.error("✗ Failed to start scheduler: %s", exc, exc_info=True)
            LOGGER.error("  Scheduled measurements will not run automatically")
            LOGGER.error("  You can still trigger measurements manually from the dashboard")

    def shutdown(self) -> None:
        if self.started:
            self.scheduler.shutdown(wait=False)
            self.started = False

    def _run_cycle(self) -> None:
        """Run measurement cycle if allowed by schedule."""
        sched_config = self._load_scheduler_config()
        now = datetime.now()
        current_day = now.strftime("%A").lower()
        current_time = now.strftime("%H:%M")
        
        if not self._should_run_now(sched_config):
            mode = sched_config.get("mode", "simple")
            if mode == "advanced":
                schedule = sched_config.get("schedule", {})
                if current_day in schedule:
                    slots = schedule[current_day]
                    LOGGER.info(
                        "Skipping measurement - %s %s is outside time slots: %s",
                        current_day.capitalize(), current_time,
                        ", ".join(f"{s['startTime']}-{s['endTime']}" for s in slots)
                    )
                else:
                    LOGGER.info("Skipping measurement - %s not configured in schedule", current_day.capitalize())
            else:
                LOGGER.info("Skipping measurement - outside scheduled time window (%s %s)", current_day.capitalize(), current_time)
            return
        
        LOGGER.info("Starting scheduled measurement cycle at %s (day: %s, time: %s)", 
                    datetime.utcnow().isoformat(), current_day.capitalize(), current_time)
        try:
            self.measurements.run_speedtest()
            self.measurements.run_bufferbloat()
            self.exporter.write_snapshot()
        except Exception as exc:  # pylint: disable=broad-except
            LOGGER.exception("Scheduled measurement failed: %s", exc)
