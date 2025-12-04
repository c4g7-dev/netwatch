#!/usr/bin/env python3
"""Test script to verify measurement storage and retrieval"""

from pathlib import Path
from datetime import datetime
from app.internal_db import init_internal_db, get_internal_session, Device, InternalMeasurement
from app.internal_manager import InternalNetworkManager

# Initialize database
data_dir = Path("data")
data_dir.mkdir(exist_ok=True)
session_factory = init_internal_db(data_dir)

# Create a test device
with get_internal_session(session_factory) as session:
    # Check if test device exists
    device = session.query(Device).filter_by(mac_address="AA:BB:CC:DD:EE:FF").first()
    if not device:
        device = Device(
            mac_address="AA:BB:CC:DD:EE:FF",
            ip_address="192.168.1.100",
            hostname="test-device",
            friendly_name="Test Device",
            connection_type="lan",
            is_local=False,
            first_seen=datetime.utcnow(),
            last_seen=datetime.utcnow(),
            is_active=True,
        )
        session.add(device)
        session.flush()
        print(f"Created test device with ID: {device.id}")
    else:
        print(f"Using existing test device with ID: {device.id}")
    
    device_id = device.id

# Create a test measurement
with get_internal_session(session_factory) as session:
    measurement = InternalMeasurement(
        timestamp=datetime.utcnow(),
        device_id=device_id,
        connection_type="lan",
        download_mbps=500.5,
        upload_mbps=100.2,
        ping_idle_ms=15.5,
        ping_loaded_ms=None,
        jitter_ms=2.5,
        packet_loss_percent=0.0,
        ping_during_download_ms=25.3,
        ping_during_upload_ms=20.1,
        bufferbloat_grade="B",
        gateway_ping_ms=1.2,
        local_latency_ms=0.8,
        test_duration_seconds=30.5,
        raw_json='{"test": "data"}',
    )
    session.add(measurement)
    print(f"Created test measurement with ID: {measurement.id}")

# Now test the manager methods
manager = InternalNetworkManager(session_factory, data_dir)

# Test 1: Get measurements via _measurement_to_dict (used by /api/internal/measurements)
print("\n=== Test 1: General measurements API ===")
measurements = manager.get_measurements(limit=1, device_id=device_id)
if measurements:
    m = measurements[0]
    print(f"Timestamp: {m.get('timestamp')}")
    print(f"download_mbps: {m.get('download_mbps')}")
    print(f"upload_mbps: {m.get('upload_mbps')}")
    print(f"ping_idle_ms: {m.get('ping_idle_ms')}")
    print(f"jitter_ms: {m.get('jitter_ms')}")
    print(f"bufferbloat_grade: {m.get('bufferbloat_grade')}")
else:
    print("ERROR: No measurements returned!")

# Test 2: Get device details (used by /api/internal/devices/{id})
print("\n=== Test 2: Device details API ===")
device_details = manager.get_device_details(device_id)
if device_details and device_details.get('measurements'):
    m = device_details['measurements'][0]
    print(f"Timestamp: {m.get('timestamp')}")
    print(f"download_speed: {m.get('download_speed')}")
    print(f"upload_speed: {m.get('upload_speed')}")
    print(f"ping_idle_ms: {m.get('ping_idle_ms')}")
    print(f"jitter: {m.get('jitter')}")
    print(f"bufferbloat_grade: {m.get('bufferbloat_grade')}")
    print(f"ping_loaded_ms: {m.get('ping_loaded_ms')}")
else:
    print("ERROR: No measurements in device details!")

# Test 3: Get devices list (used by /api/internal/devices)
print("\n=== Test 3: Devices list API ===")
devices = manager.get_devices()
if devices:
    d = [dev for dev in devices if dev['id'] == device_id][0]
    print(f"Device ID: {d.get('id')}")
    print(f"Friendly name: {d.get('friendly_name')}")
    print(f"Last download: {d.get('last_download')}")
    print(f"Last upload: {d.get('last_upload')}")
    print(f"Last ping: {d.get('last_ping')}")
    print(f"Last jitter: {d.get('last_jitter')}")
    print(f"Last test: {d.get('last_test')}")
else:
    print("ERROR: No devices returned!")

print("\n=== Tests complete ===")
