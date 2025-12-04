# NetWatch Metrics Guide

## Internet Tab Metrics

### Speed Metrics
- **Download (Mbps)** - Download speed from internet speedtest server
- **Upload (Mbps)** - Upload speed to internet speedtest server

### Latency Metrics
- **Ping (ms)** - Idle ping to speedtest server (baseline latency with no load)
- **Jitter (ms)** - Variation in ping time (network stability indicator)

### Bufferbloat Metrics
These show how latency degrades under network load:

- **Ping (Download)** - Latency measured WHILE downloading data
  - High values indicate bufferbloat on download path
  - Ideally should be close to idle ping
  
- **Ping (Upload)** - Latency measured WHILE uploading data  
  - High values indicate bufferbloat on upload path
  - Most common bufferbloat issue location

- **Download Latency** - Interquartile mean (IQM) latency during download
  - More stable average than raw ping measurements
  - From Ookla speedtest `download.latency.iqm` field

- **Upload Latency** - Interquartile mean (IQM) latency during upload
  - More stable average than raw ping measurements  
  - From Ookla speedtest `upload.latency.iqm` field

## Homenet Tab Metrics

### Speed Metrics (same as Internet)
- **Download (Mbps)** - Speed from internal speedtest server
- **Upload (Mbps)** - Speed to internal speedtest server

### Latency Metrics
- **Ping (ms)** - Idle ping to speedtest server (speedtest-cli)
- **Jitter (ms)** - Ping variation
- **Gateway Ping (ms)** - Ping to your local router/gateway (e.g., 192.168.0.1)
  - Shows local network latency
  - Should be <5ms for healthy LAN
- **Local Latency (ms)** - Round-trip time to gateway
  - Same measurement as Gateway Ping
  - Alternative name for same metric
- **Loaded Ping (ms)** - Max of `ping_during_download_ms` or `ping_during_upload_ms`
  - Shows worst-case latency under load
  - Indicates bufferbloat on your local network or ISP

### Charts
1. **LAN Speed History** - Download/Upload over time
2. **LAN Latency History** - Ping, Jitter, Gateway Ping, Local Latency
3. **Bufferbloat (Latency Under Load)** - Idle Ping vs Loaded Ping vs Gateway Ping

## Troubleshooting Missing Metrics

### If Gateway Ping / Local Latency / Loaded Ping are missing in charts:

1. **Check if measurements have the data:**
   ```bash
   python -c "from app.internal_db import *; from pathlib import Path; from sqlalchemy import desc; sf = init_internal_db(Path('data')); from sqlalchemy.orm import Session; s = sf(); m = s.query(InternalMeasurement).order_by(desc(InternalMeasurement.timestamp)).first(); print(f'Gateway: {m.gateway_ping_ms}, Local: {m.local_latency_ms}, Loaded: {m.ping_during_download_ms}/{m.ping_during_upload_ms}'); s.close()"
   ```

2. **If values are NULL:**
   - Old measurements don't have these fields (feature added recently)
   - Run a NEW speedtest in the Homenet tab
   - New measurements will include all metrics

3. **If still NULL after new test:**
   - Check gateway detection: `ip route | grep default` (Linux) or `route print` (Windows)
   - Gateway must be reachable on local network
   - Check logs for "Selected LAN gateway" messages

4. **Clear browser cache:**
   ```bash
   # Hard refresh browser
   Ctrl+F5 (Windows/Linux)
   Cmd+Shift+R (Mac)
   ```

5. **Verify JavaScript version:**
   - Check page source for `dashboard.js?v=34` (or higher)
   - If lower version, pull latest code and restart server

## Data Sources

### Internet Tab Data
- Source: `data/metrics.db` → `measurements` table
- Collected by: Ookla speedtest CLI or speedtest-cli fallback
- Fields populated: All fields including `ping_during_download_ms`, `download_latency_ms`, etc.

### Homenet Tab Data
- Source: `data/internal_metrics.db` → `internal_measurements` table
- Collected by: Internal speedtest server + speedtest-cli
- Fields populated: All fields including `gateway_ping_ms`, `local_latency_ms`, etc.

## Expected Values

### Good Network
- **Idle Ping**: 1-30ms (internet), <5ms (gateway)
- **Jitter**: <5ms
- **Loaded Ping**: <50ms increase from idle
- **Bufferbloat Grade**: A or B

### Problem Indicators
- **Idle Ping**: >100ms = poor routing or distance
- **Jitter**: >20ms = unstable connection
- **Loaded Ping**: >100ms increase = severe bufferbloat
- **Gateway Ping**: >10ms = local network issue
- **Bufferbloat Grade**: D or F = significant bufferbloat
