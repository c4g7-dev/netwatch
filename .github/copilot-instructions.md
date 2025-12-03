# NetWatch Copilot Instructions

## Architecture Overview

NetWatch is a self-hosted network performance monitor with two measurement systems:

1. **Internet Monitoring** (`app/measurements/`) - Ookla speedtest + iperf3 bufferbloat testing
2. **Internal/Homenet Monitoring** (`app/internal_*.py`) - LAN device scanning and local network speed tests

### Key Components

```
main.py → app/__init__.py (bootstrap) → ApplicationContext
                                        ├── MeasurementManager (internet tests)
                                        ├── InternalNetworkManager (LAN tests)
                                        ├── SchedulerService (APScheduler)
                                        └── Flask app (app/web/app.py)
```

### Database Architecture

- **Internet metrics**: `data/metrics.db` - `Measurement` model in `app/db.py`
- **Internal metrics**: `data/internal_metrics.db` - `Device` + `InternalMeasurement` models in `app/internal_db.py`
- Both use SQLAlchemy ORM with SQLite; use `get_session()` / `get_internal_session()` context managers

## Developer Workflow

```bash
# Activate venv (required)
.venv\Scripts\activate  # Windows
source .venv/bin/activate  # Linux/macOS

# Start server
python main.py --debug  # Development with auto-reload
python main.py --port 8080  # Override port

# Delete internal DB to reset schema (when adding columns)
Remove-Item data/internal_metrics.db -Force  # PowerShell
```

## Code Patterns

### Flask Routes
Routes defined inline in `create_web_app()` factory. Background tasks use `ThreadPoolExecutor`:
```python
executor.submit(_run_speedtest_task, manager, exporter)
return jsonify({"status": "queued"}), 202
```

### SSE Streaming (Internal Speedtest)
`/api/internal/speedtest/stream` yields Server-Sent Events:
```python
yield {"event": "metric", "data": {"name": "download", "value": 500.5}}
yield {"event": "phase", "data": {"phase": "upload", "message": "Testing upload..."}}
yield {"event": "complete", "data": {"results": {...}}}
```

### Device-Measurement Linking
Measurements link to devices via `device_id`. Resolution flow:
1. Explicit `device_id` query param, OR
2. Auto-resolve from client IP via `resolve_device_id_by_ip()`

### Frontend (dashboard.js)
- State: `state` (internet), `internalState` (homenet with `devices`, `measurements`)
- Charts: Chart.js instances in `charts` / `internalCharts` objects
- View toggle: `localStorage.getItem('netwatch_current_view')` persists 'internet' | 'homenet'
- Cache busting: Update `?v=XX` in index.html when editing JS

## Common Tasks

### Adding a new internal measurement field
1. Add column to `InternalMeasurement` in `app/internal_db.py`
2. Update `_store_measurement()` in `app/internal_manager.py`
3. Update `_measurement_to_dict()` to include new field
4. Delete `data/internal_metrics.db` and restart server
5. Update frontend display in `dashboard.js`

### Adding API endpoint
Add route inside `create_web_app()` in `app/web/app.py`:
```python
@app.get("/api/internal/new-endpoint")
def api_new_endpoint():
    return jsonify(internal_manager.some_method())
```

### Scheduler Configuration
UI-driven config stored in `data/scheduler_config.json`. Three modes: `simple`, `weekly`, `advanced`.

## Testing Notes

- No test suite currently - test manually via browser + API calls
- Check server logs for errors during speedtest execution
- Device scanning uses ARP cache + ping; may require elevated privileges on some systems
