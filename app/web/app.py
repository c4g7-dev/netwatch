"""Flask application factory and HTTP routes."""

from __future__ import annotations

import json
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
from ..internal_db import init_internal_db
from ..internal_manager import InternalNetworkManager, InternalCSVExporter

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

    executor = ThreadPoolExecutor(max_workers=4)
    
    # Initialize internal network manager
    data_dir = Path("data")
    data_dir.mkdir(exist_ok=True)
    internal_session_factory = init_internal_db(data_dir)
    internal_manager = InternalNetworkManager(internal_session_factory, data_dir)
    internal_exporter = InternalCSVExporter(internal_session_factory, data_dir)
    
    # Auto-start the speedtest server on app startup
    LOGGER.info("Starting internal speedtest server...")
    if internal_manager.start_server():
        LOGGER.info("✓ Internal speedtest server started successfully on port 5201")
    else:
        LOGGER.error("✗ Failed to start internal speedtest server - check logs for details")
        LOGGER.error("  The homenet speedtest feature will not be available")
        LOGGER.error("  Common issues:")
        LOGGER.error("    - Port 5201 already in use by another service")
        LOGGER.error("    - Permission denied (check systemd service configuration)")

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
                "auto_download_ookla": config.ookla.auto_download,
            }
        )

    @app.get("/api/scheduler/config")
    def api_get_scheduler_config():
        """Get current scheduler configuration."""
        config_file = Path("data/scheduler_config.json")
        if not config_file.exists():
            # Return default config
            return jsonify({
                "mode": "simple",
                "enabled": True,
                "interval": 30
            })
        
        try:
            with open(config_file, "r") as f:
                return jsonify(json.load(f))
        except Exception as e:
            LOGGER.error(f"Failed to read scheduler config: {e}")
            return jsonify({"error": "Failed to read configuration"}), 500

    @app.post("/api/scheduler/config")
    def api_save_scheduler_config():
        """Save scheduler configuration to file."""
        
        config_data = request.get_json()
        if not config_data:
            return jsonify({"error": "No configuration data provided"}), 400
        
        # Validate mode
        if "mode" not in config_data or config_data["mode"] not in ["simple", "weekly", "advanced"]:
            return jsonify({"error": "Invalid mode specified"}), 400
        
        config_file = Path("data/scheduler_config.json")
        config_file.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            with open(config_file, "w") as f:
                json.dump(config_data, f, indent=2)
            
            LOGGER.info(f"Scheduler configuration saved: {config_data.get('mode')} mode")
            
            # Reload scheduler with new configuration
            scheduler.reload_config()
            
            return jsonify({"status": "success", "message": "Configuration saved"})
        except Exception as e:
            LOGGER.error(f"Failed to save scheduler config: {e}")
            return jsonify({"error": "Failed to save configuration"}), 500

    # =========================================================================
    # Internal Network API Endpoints
    # =========================================================================

    @app.get("/api/internal/summary")
    def api_internal_summary():
        """Get internal network summary."""
        return jsonify(internal_manager.get_summary())

    @app.get("/api/internal/devices")
    def api_internal_devices():
        """Get list of network devices."""
        include_offline = request.args.get("include_offline", "false").lower() == "true"
        return jsonify(internal_manager.get_devices(include_offline=include_offline))

    @app.post("/api/internal/devices/scan")
    def api_internal_scan_devices():
        """Scan network for devices."""
        quick = request.args.get("quick", "true").lower() == "true"
        devices = internal_manager.scan_devices(quick=quick)
        return jsonify({"status": "success", "devices": devices})

    @app.get("/api/internal/devices/<int:device_id>")
    def api_internal_device(device_id: int):
        """Get specific device details."""
        device = internal_manager.get_device_details(device_id)
        if not device:
            return jsonify({"error": "Device not found"}), 404
        return jsonify(device)

    @app.put("/api/internal/devices/<int:device_id>")
    def api_internal_update_device(device_id: int):
        """Update device information (e.g., friendly name)."""
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400
        
        result = internal_manager.update_device(device_id, data)
        if not result:
            return jsonify({"error": "Device not found"}), 404
        return jsonify(result)

    @app.get("/api/internal/measurements")
    def api_internal_measurements():
        """Get internal network measurements."""
        start = _parse_datetime(request.args.get("start"))
        end = _parse_datetime(request.args.get("end"))
        limit = request.args.get("limit", type=int)
        device_id = request.args.get("device_id", type=int)
        connection_type = request.args.get("connection_type")
        
        measurements = internal_manager.get_measurements(
            limit=limit,
            start=start,
            end=end,
            device_id=device_id,
            connection_type=connection_type,
        )
        return jsonify(measurements)

    def _resolve_device_id(requested_id: Optional[int], auto_register: bool = False) -> Optional[int]:
        """Resolve device ID by falling back to client's IP address.
        
        Args:
            requested_id: Explicitly requested device ID
            auto_register: If True, auto-register unknown devices
        """
        if requested_id:
            return requested_id
        client_ip = request.headers.get("X-Forwarded-For", request.remote_addr)
        if not client_ip:
            LOGGER.debug("No client IP available for device resolution")
            return None
        if "," in client_ip:
            client_ip = client_ip.split(",")[0].strip()
        LOGGER.debug(f"Resolving device ID for client IP: {client_ip}")
        resolved_id = internal_manager.resolve_device_id_by_ip(client_ip, auto_register=auto_register)
        LOGGER.debug(f"Resolved device ID: {resolved_id}")
        return resolved_id

    @app.post("/api/internal/speedtest")
    def api_internal_speedtest():
        """Run internal network speedtest (non-streaming)."""
        requested_id = request.args.get("device_id", type=int)
        # Auto-register device if not found - they're running a speedtest so we want to track them
        device_id = _resolve_device_id(requested_id, auto_register=True)
        executor.submit(_run_internal_speedtest_task, internal_manager, device_id)
        return jsonify({"status": "queued", "task": "internal_speedtest"}), 202

    @app.get("/api/internal/speedtest/stream")
    def api_internal_speedtest_stream():
        """Run internal network speedtest with SSE streaming progress."""
        requested_id = request.args.get("device_id", type=int)
        # Auto-register device if not found - they're running a speedtest so we want to track them
        device_id = _resolve_device_id(requested_id, auto_register=True)
        
        def generate():
            for event in internal_manager.run_speedtest_stream(device_id):
                event_type = event.get("event", "message")
                data = json.dumps(event.get("data", {}))
                yield f"event: {event_type}\ndata: {data}\n\n"
        
        return Response(
            generate(),
            mimetype="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",  # For nginx
            }
        )

    @app.get("/api/internal/server/status")
    def api_internal_server_status():
        """Get internal speedtest server status."""
        return jsonify(internal_manager.get_server_status())

    @app.post("/api/internal/server/start")
    def api_internal_server_start():
        """Start internal speedtest server."""
        success = internal_manager.start_server()
        if success:
            return jsonify({"status": "success", "message": "Server started"})
        return jsonify({"error": "Failed to start server"}), 500

    @app.post("/api/internal/server/stop")
    def api_internal_server_stop():
        """Stop internal speedtest server."""
        success = internal_manager.stop_server()
        if success:
            return jsonify({"status": "success", "message": "Server stopped"})
        return jsonify({"error": "Failed to stop server"}), 500

    @app.get("/api/internal/export/csv")
    def api_internal_export_csv():
        """Export internal measurements as CSV."""
        scope = request.args.get("scope", "filtered")
        start = _parse_datetime(request.args.get("start")) if scope == "filtered" else None
        end = _parse_datetime(request.args.get("end")) if scope == "filtered" else None
        device_id = request.args.get("device_id", type=int)
        
        buffer = internal_exporter.build_csv(start=start, end=end, device_id=device_id)
        filename = f"internal-results-{datetime.utcnow().strftime('%Y%m%dT%H%M%S')}.csv"
        return Response(
            buffer.getvalue(),
            mimetype="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )

    @app.get("/api/internal/export/devices")
    def api_internal_export_devices():
        """Export device list as CSV."""
        buffer = internal_exporter.build_devices_csv()
        filename = f"devices-{datetime.utcnow().strftime('%Y%m%dT%H%M%S')}.csv"
        return Response(
            buffer.getvalue(),
            mimetype="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
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


def _run_internal_speedtest_task(internal_manager: InternalNetworkManager, device_id: Optional[int] = None):
    """Run internal speedtest in background."""
    try:
        result = internal_manager.run_speedtest(device_id)
        if "error" in result:
            LOGGER.error(f"Internal speedtest failed: {result['error']}")
        else:
            LOGGER.info(f"Internal speedtest completed: {result['results'].get('download_mbps', 0):.1f} Mbps down / {result['results'].get('upload_mbps', 0):.1f} Mbps up")
    except Exception as e:
        LOGGER.error(f"Internal speedtest task failed: {e}")
