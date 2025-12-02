"""Flask application factory and HTTP routes."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Optional

from flask import Flask, Response, jsonify, render_template, request
from werkzeug.middleware.proxy_fix import ProxyFix

from ..config import AppConfig
from ..exporter import CSVExporter
from ..measurements.manager import MeasurementManager
from ..scheduler import SchedulerService

LOGGER = logging.getLogger(__name__)


def create_web_app(
    config: AppConfig,
    session_factory,
    measurement_manager: MeasurementManager,
    exporter: CSVExporter,
    scheduler: SchedulerService,
) -> Flask:
    template_folder = Path(__file__).resolve().parent / "templates"
    static_folder = Path(__file__).resolve().parent / "static"

    app = Flask(__name__, template_folder=template_folder, static_folder=static_folder)
    app.config["SECRET_KEY"] = config.web.secret_key
    app.config["SESSION_FACTORY"] = session_factory

    if config.web.reverse_proxy_headers:
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)  # type: ignore

    executor = ThreadPoolExecutor(max_workers=2)

    @app.route("/")
    def index():
        return render_template("index.html", config=config)

    @app.get("/api/measurements")
    def api_measurements():
        start = _parse_datetime(request.args.get("start"))
        end = _parse_datetime(request.args.get("end"))
        limit = request.args.get("limit", type=int)
        measurement_type = request.args.get("type")
        rows = measurement_manager.get_measurements(limit=limit, start=start, end=end, measurement_type=measurement_type)
        return jsonify([measurement_manager.to_dict(row) for row in rows])

    @app.get("/api/summary/latest")
    def api_latest_summary():
        rows = measurement_manager.latest_two()
        if not rows:
            return jsonify({"latest": None, "previous": None, "delta": None})
        latest = measurement_manager.to_dict(rows[0])
        previous = measurement_manager.to_dict(rows[1]) if len(rows) > 1 else None
        delta = _calculate_delta(latest, previous) if previous else None
        return jsonify({"latest": latest, "previous": previous, "delta": delta})

    @app.get("/api/export/csv")
    def api_export_csv():
        scope = request.args.get("scope", "filtered")
        start = _parse_datetime(request.args.get("start")) if scope == "filtered" else None
        end = _parse_datetime(request.args.get("end")) if scope == "filtered" else None
        buffer = exporter.build_csv(start=start, end=end)
        filename = f"results-{datetime.utcnow().strftime('%Y%m%dT%H%M%S')}.csv"
        return Response(
            buffer.getvalue(),
            mimetype="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )

    @app.post("/api/manual/speedtest")
    def api_manual_speedtest():
        executor.submit(_run_speedtest_task, measurement_manager, exporter)
        return jsonify({"status": "queued", "task": "speedtest"}), 202

    @app.post("/api/manual/bufferbloat")
    def api_manual_bufferbloat():
        executor.submit(_run_bufferbloat_task, measurement_manager, exporter)
        return jsonify({"status": "queued", "task": "bufferbloat"}), 202

    @app.get("/api/status")
    def api_status():
        return jsonify(
            {
                "scheduler_enabled": config.scheduler.enabled,
                "scheduler_interval_minutes": config.scheduler.interval_minutes,
                "auto_download_ookla": config.ookla.auto_download,
            }
        )

    return app


def _parse_datetime(raw: Optional[str]) -> Optional[datetime]:
    if not raw:
        return None
    candidate = raw.replace("Z", "+00:00") if raw.endswith("Z") else raw
    try:
        return datetime.fromisoformat(candidate)
    except ValueError:
        LOGGER.warning("Invalid datetime filter: %s", raw)
        return None


def _calculate_delta(latest: dict, previous: dict) -> dict:
    def diff(key):
        latest_value = latest.get(key)
        previous_value = previous.get(key)
        if latest_value is None or previous_value is None:
            return None
        return latest_value - previous_value

    fields = [
        "download",
        "upload",
        "ping_idle",
        "jitter",
        "ping_under_download",
        "ping_under_upload",
    ]
    return {field: diff(field) for field in fields}


def _run_speedtest_task(manager: MeasurementManager, exporter: CSVExporter):
    manager.run_speedtest()
    exporter.write_snapshot()


def _run_bufferbloat_task(manager: MeasurementManager, exporter: CSVExporter):
    manager.run_bufferbloat()
    exporter.write_snapshot()
