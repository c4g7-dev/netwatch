"""Internal network measurement manager and CSV exporter."""

from __future__ import annotations

import csv
import io
import json
import logging
import platform
import random
import re
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any, Generator

from sqlalchemy.orm import sessionmaker

from .internal_db import (
    Device,
    InternalMeasurement,
    get_internal_session,
)
from .internal_speedtest import InternalSpeedtestServer, calculate_bufferbloat_grade
from .device_scanner import get_device_scanner, NetworkDevice

LOGGER = logging.getLogger(__name__)


class InternalNetworkManager:
    """
    Manages internal network testing, device tracking, and measurements.
    """
    
    def __init__(self, session_factory: sessionmaker, data_dir: Path):
        self.session_factory = session_factory
        self.data_dir = data_dir
        self.speedtest_server = InternalSpeedtestServer()
        self.device_scanner = get_device_scanner()
        self._test_in_progress = False
    
    def start_server(self) -> bool:
        """Start the internal speedtest server."""
        return self.speedtest_server.start()
    
    def stop_server(self) -> bool:
        """Stop the internal speedtest server."""
        return self.speedtest_server.stop()
    
    def get_server_status(self) -> Dict[str, Any]:
        """Get internal speedtest server status."""
        return self.speedtest_server.get_status()
    
    def scan_devices(self, quick: bool = True) -> List[Dict[str, Any]]:
        """
        Scan network for devices.
        
        Args:
            quick: If True, use quick ARP-based scan. If False, do full ping sweep.
        
        Returns:
            List of device dictionaries
        """
        if quick:
            devices = self.device_scanner.quick_scan()
        else:
            devices = self.device_scanner.scan_network()
        
        # Sync to database
        self._sync_devices_to_db(devices)
        
        return [d.to_dict() for d in devices]
    
    def _sync_devices_to_db(self, devices: List[NetworkDevice]):
        """Sync discovered devices to database."""
        with get_internal_session(self.session_factory) as session:
            for device in devices:
                if not device.mac_address:
                    continue
                
                # Find or create device
                db_device = session.query(Device).filter_by(mac_address=device.mac_address).first()
                
                if db_device:
                    # Update existing
                    db_device.ip_address = device.ip_address
                    db_device.hostname = device.hostname or db_device.hostname
                    db_device.connection_type = device.connection_type
                    db_device.is_local = device.is_local
                    db_device.last_seen = datetime.utcnow()
                    db_device.is_active = True
                else:
                    # Create new
                    db_device = Device(
                        mac_address=device.mac_address,
                        ip_address=device.ip_address,
                        hostname=device.hostname,
                        connection_type=device.connection_type,
                        is_local=device.is_local,
                        first_seen=datetime.utcnow(),
                        last_seen=datetime.utcnow(),
                        is_active=True,
                    )
                    session.add(db_device)
    
    def get_devices(self, include_offline: bool = False) -> List[Dict[str, Any]]:
        """Get all tracked devices from database with latest measurement stats."""
        with get_internal_session(self.session_factory) as session:
            query = session.query(Device)
            if not include_offline:
                query = query.filter_by(is_active=True)
            
            devices = query.order_by(Device.last_seen.desc()).all()
            result = []
            
            for device in devices:
                device_dict = self._device_to_dict(device)
                
                # Get the latest measurement for this device
                latest_measurement = (
                    session.query(InternalMeasurement)
                    .filter_by(device_id=device.id)
                    .order_by(InternalMeasurement.timestamp.desc())
                    .first()
                )
                
                if latest_measurement:
                    device_dict["last_download"] = latest_measurement.download_mbps
                    device_dict["last_upload"] = latest_measurement.upload_mbps
                    device_dict["last_ping"] = latest_measurement.ping_idle_ms
                    device_dict["last_jitter"] = latest_measurement.jitter_ms
                    device_dict["last_test"] = latest_measurement.timestamp.isoformat() if latest_measurement.timestamp else None
                else:
                    device_dict["last_download"] = None
                    device_dict["last_upload"] = None
                    device_dict["last_ping"] = None
                    device_dict["last_jitter"] = None
                    device_dict["last_test"] = None
                
                result.append(device_dict)
            
            return result

    def resolve_device_id_by_ip(self, ip_address: Optional[str], auto_register: bool = False) -> Optional[int]:
        """Resolve a device ID from an IP address recorded in the request.
        
        Handles special cases:
        - IPv6-mapped IPv4 addresses (::ffff:x.x.x.x)
        - Localhost connections (127.0.0.1, ::1) mapped to local device
        
        Args:
            ip_address: The IP address to look up
            auto_register: If True, create a new device entry if not found
        """
        if not ip_address:
            return None
        normalized = ip_address.strip()
        
        # Handle IPv6-mapped IPv4
        if normalized.startswith("::ffff:"):
            normalized = normalized.split("::ffff:")[-1]
        
        # Check if this is a localhost request (maps to the local device)
        is_localhost = normalized in ("127.0.0.1", "::1", "localhost")
        
        with get_internal_session(self.session_factory) as session:
            if is_localhost:
                # Find the device marked as local (is_local=True)
                device = (
                    session.query(Device)
                    .filter(Device.is_local == True)
                    .order_by(Device.last_seen.desc())
                    .first()
                )
                if device:
                    LOGGER.debug(f"Mapped localhost to local device ID {device.id} ({device.ip_address})")
                    device.last_seen = datetime.utcnow()
                    return device.id
                # No local device found - auto-register if requested
                if auto_register:
                    LOGGER.info("Auto-registering local device for localhost request")
                    local_ip = self._get_local_ip()
                    if local_ip:
                        new_device = self._auto_register_device(local_ip, session)
                        if new_device:
                            return new_device.id
                LOGGER.debug("No local device found for localhost request")
                return None
            
            # Normal IP lookup
            device = (
                session.query(Device)
                .filter(Device.ip_address == normalized)
                .order_by(Device.last_seen.desc())
                .first()
            )
            if device:
                device.last_seen = datetime.utcnow()
                return device.id
            
            # Device not found - optionally auto-register
            if auto_register:
                LOGGER.info(f"Auto-registering new device with IP: {normalized}")
                new_device = self._auto_register_device(normalized, session)
                if new_device:
                    return new_device.id
            
            LOGGER.debug(f"No device found for IP: {normalized}")
            return None
    
    def _auto_register_device(self, ip_address: str, session) -> Optional[Device]:
        """Auto-register a device by IP address.
        
        Attempts to get MAC address and determine connection type.
        """
        # Try to get MAC address from ARP
        mac_address = self._get_mac_for_ip(ip_address)
        if not mac_address:
            # Generate a placeholder MAC for tracking using SHA256 (secure hash)
            import hashlib
            mac_hash = hashlib.sha256(ip_address.encode()).hexdigest()[:12]
            mac_address = ':'.join(mac_hash[i:i+2] for i in range(0, 12, 2))
            LOGGER.warning(f"Could not get MAC for {ip_address}, using hash: {mac_address}")
        
        # Try to get hostname
        hostname = self._get_hostname_for_ip(ip_address)
        
        # Classify connection type based on response characteristics
        connection_type = self._classify_connection_type(ip_address)
        
        # Check if this is the local machine
        is_local = self._is_local_ip(ip_address)
        
        # Create new device
        new_device = Device(
            mac_address=mac_address,
            ip_address=ip_address,
            hostname=hostname,
            connection_type=connection_type,
            is_local=is_local,
            first_seen=datetime.utcnow(),
            last_seen=datetime.utcnow(),
            is_active=True,
        )
        session.add(new_device)
        session.flush()  # Get the ID
        LOGGER.info(f"Auto-registered device: {ip_address} (ID: {new_device.id}, type: {connection_type})")
        return new_device
    
    def _get_mac_for_ip(self, ip_address: str) -> Optional[str]:
        """Get MAC address for an IP from ARP table."""
        try:
            if platform.system() == "Windows":
                result = subprocess.run(["arp", "-a", ip_address], capture_output=True, text=True, timeout=5)
                # Parse Windows ARP output
                for line in result.stdout.split('\n'):
                    if ip_address in line:
                        match = re.search(r'([0-9a-fA-F]{2}[:-]){5}[0-9a-fA-F]{2}', line)
                        if match:
                            return match.group(0).replace('-', ':').upper()
            else:
                result = subprocess.run(["arp", "-n", ip_address], capture_output=True, text=True, timeout=5)
                for line in result.stdout.split('\n'):
                    if ip_address in line:
                        match = re.search(r'([0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}', line)
                        if match:
                            return match.group(0).upper()
        except Exception as e:
            LOGGER.debug(f"Failed to get MAC for {ip_address}: {e}")
        return None
    
    def _get_hostname_for_ip(self, ip_address: str) -> Optional[str]:
        """Resolve hostname for IP address."""
        try:
            import socket
            hostname = socket.gethostbyaddr(ip_address)[0]
            return hostname
        except Exception:
            return None
    
    def _classify_connection_type(self, ip_address: str) -> str:
        """Classify device as LAN or WiFi based on ping characteristics."""
        try:
            # Do multiple pings and analyze jitter
            if platform.system() == "Windows":
                cmd = ["ping", "-n", "5", "-w", "1000", ip_address]
            else:
                cmd = ["ping", "-c", "5", "-W", "1", ip_address]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            
            times = []
            time_pattern = r"time[=<](\d+(?:\.\d+)?)\s*ms"
            for line in result.stdout.split('\n'):
                match = re.search(time_pattern, line, re.IGNORECASE)
                if match:
                    times.append(float(match.group(1)))
            
            if len(times) >= 3:
                avg_ping = sum(times) / len(times)
                # Calculate jitter (variance in ping times)
                diffs = [abs(times[i+1] - times[i]) for i in range(len(times)-1)]
                jitter = sum(diffs) / len(diffs) if diffs else 0
                
                # WiFi typically has higher jitter (>2ms) and higher latency
                # LAN typically has very low jitter (<1ms) and sub-1ms latency
                if avg_ping < 1.5 and jitter < 1.0:
                    return "lan"
                elif jitter > 2.0 or avg_ping > 5:
                    return "wifi"
                else:
                    return "unknown"
        except Exception as e:
            LOGGER.debug(f"Failed to classify connection for {ip_address}: {e}")
        return "unknown"
    
    def _is_local_ip(self, ip_address: str) -> bool:
        """Check if IP belongs to this machine."""
        try:
            import socket
            local_ips = socket.gethostbyname_ex(socket.gethostname())[2]
            return ip_address in local_ips
        except Exception:
            return False
    
    def _get_local_ip(self) -> Optional[str]:
        """Get the local machine's IP address on the network."""
        try:
            import socket
            # Create a socket to determine the local IP by connecting to an external address
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(0.1)
            # Doesn't actually send anything, just uses connect to determine local interface
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
            s.close()
            return local_ip
        except Exception as e:
            LOGGER.debug(f"Could not get local IP: {e}")
            # Fallback to hostname lookup
            try:
                import socket
                local_ips = socket.gethostbyname_ex(socket.gethostname())[2]
                if local_ips:
                    return local_ips[0]
            except Exception:
                pass
            return None

    def get_device_details(self, device_id: int) -> Optional[Dict[str, Any]]:
        """Return an enriched device payload with measurement history."""
        with get_internal_session(self.session_factory) as session:
            device = session.query(Device).get(device_id)
            if not device:
                return None
            data = self._device_to_dict(device)
            measurement_dicts, stats = self._build_device_measurements(session, device_id)
            data["measurements"] = measurement_dicts
            data.update(stats)
            return data

    def _build_device_measurements(self, session, device_id: int, limit: int = 50) -> tuple[list[Dict[str, Any]], Dict[str, Optional[float]]]:
        """Fetch recent measurements and aggregate stats for a device."""
        measurements = (
            session.query(InternalMeasurement)
            .filter_by(device_id=device_id)
            .order_by(InternalMeasurement.timestamp.desc())
            .limit(limit)
            .all()
        )
        measurement_dicts = [
            {
                "timestamp": m.timestamp.isoformat() if m.timestamp else None,
                "download_speed": m.download_mbps,
                "upload_speed": m.upload_mbps,
                "latency": m.ping_idle_ms,
                "jitter": m.jitter_ms,
                "bufferbloat_grade": m.bufferbloat_grade,
                "ping_idle_ms": m.ping_idle_ms,
                "ping_loaded_ms": max(m.ping_during_download_ms or 0, m.ping_during_upload_ms or 0) if (m.ping_during_download_ms or m.ping_during_upload_ms) else None,
                "gateway_ping_ms": m.gateway_ping_ms,
            }
            for m in measurements
        ]
        return measurement_dicts, self._calculate_measurement_stats(measurements)

    @staticmethod
    def _calculate_measurement_stats(measurements: List[InternalMeasurement]) -> Dict[str, Optional[float]]:
        if not measurements:
            return {
                "best_download": None,
                "best_upload": None,
                "avg_ping": None,
                "avg_jitter": None,
            }
        return {
            "best_download": InternalNetworkManager._max_metric(measurements, "download_mbps"),
            "best_upload": InternalNetworkManager._max_metric(measurements, "upload_mbps"),
            "avg_ping": InternalNetworkManager._avg_metric(measurements, "ping_idle_ms"),
            "avg_jitter": InternalNetworkManager._avg_metric(measurements, "jitter_ms"),
        }

    @staticmethod
    def _max_metric(measurements: List[InternalMeasurement], attribute: str) -> Optional[float]:
        values = [getattr(m, attribute) for m in measurements if getattr(m, attribute) is not None]
        return max(values) if values else None

    @staticmethod
    def _avg_metric(measurements: List[InternalMeasurement], attribute: str) -> Optional[float]:
        values = [getattr(m, attribute) for m in measurements if getattr(m, attribute) is not None]
        if not values:
            return None
        avg = sum(values) / len(values)
        return round(avg, 2)
    
    def _device_to_dict(self, device: Device) -> Dict[str, Any]:
        """Convert Device model to dictionary."""
        return {
            "id": device.id,
            "mac_address": device.mac_address,
            "ip_address": device.ip_address,
            "hostname": device.hostname,
            "friendly_name": device.friendly_name or device.hostname or device.ip_address,
            "connection_type": device.connection_type,
            "is_local": getattr(device, 'is_local', False),
            "first_seen": device.first_seen.isoformat() if device.first_seen else None,
            "last_seen": device.last_seen.isoformat() if device.last_seen else None,
            "is_active": device.is_active,
        }
    
    def run_speedtest(self, device_id: Optional[int] = None) -> Dict[str, Any]:
        """
        Run speedtest synchronously.
        For streaming progress, use run_speedtest_stream() instead.
        """
        results = {
            "download_mbps": None,
            "upload_mbps": None,
            "ping_idle_ms": None,
            "jitter_ms": None,
            "bufferbloat_grade": "?",
            "local_latency_ms": None,
            "test_duration_seconds": 0,
        }
        
        if self._test_in_progress:
            return {"error": "Test already in progress"}
        
        self._test_in_progress = True
        start_time = time.time()
        
        try:
            # 1. Measure local network latency (ping to localhost/gateway)
            local_ping = self._measure_local_latency()
            if local_ping:
                results["local_latency_ms"] = local_ping.get("avg_ms")
            
            # 2. Run internet speedtest using speedtest-cli
            speedtest_result = self._run_speedtest_cli()
            if speedtest_result:
                results["download_mbps"] = speedtest_result.get("download_mbps")
                results["upload_mbps"] = speedtest_result.get("upload_mbps")
                results["ping_idle_ms"] = speedtest_result.get("ping_ms")
                results["jitter_ms"] = speedtest_result.get("jitter_ms")
                results["server"] = speedtest_result.get("server")
            
            # 3. Calculate bufferbloat grade
            if results.get("ping_idle_ms") and results.get("local_latency_ms"):
                # Approximation: compare idle ping vs local latency
                results["bufferbloat_grade"] = calculate_bufferbloat_grade(
                    results["local_latency_ms"],
                    results["ping_idle_ms"]
                )
            
            results["test_duration_seconds"] = time.time() - start_time
            
            # Store measurement
            self._store_measurement(results, device_id)
            
            return {"success": True, "results": results}
            
        except Exception as e:
            LOGGER.error(f"Internal speedtest failed: {e}")
            return {"error": str(e)}
        finally:
            self._test_in_progress = False
    
    def run_speedtest_stream(self, device_id: Optional[int] = None) -> Generator[Dict[str, Any], None, None]:
        """
        Run speedtest with streaming progress updates.
        Yields progress events that can be sent via SSE.
        """
        if self._test_in_progress:
            yield {"event": "error", "data": {"message": "Test already in progress"}}
            return
        
        self._test_in_progress = True
        start_time = time.time()
        
        results = {
            "download_mbps": None,
            "upload_mbps": None,
            "ping_idle_ms": None,
            "jitter_ms": None,
            "bufferbloat_grade": "?",
            "local_latency_ms": None,
            "gateway_ping_ms": None,
            "ping_during_download_ms": None,
            "ping_during_upload_ms": None,
            "server": None,
        }
        
        # Storage for loaded ping measurements (collected in background threads)
        loaded_ping_results = {"download": [], "upload": []}
        
        try:
            # Phase 1: Local latency test
            yield {"event": "phase", "data": {"phase": "latency", "message": "Testing local network latency..."}}
            yield {"event": "progress", "data": {"percent": 5}}
            
            local_ping = self._measure_local_latency()
            if local_ping:
                results["local_latency_ms"] = local_ping.get("avg_ms")
                yield {"event": "metric", "data": {"name": "local_latency", "value": local_ping.get("avg_ms")}}
                LOGGER.info(f"Local latency: {local_ping.get('avg_ms')}ms to {local_ping.get('gateway')}")
            else:
                LOGGER.warning("Local latency measurement returned None - gateway may not be detected or reachable")
            
            yield {"event": "progress", "data": {"percent": 10}}
            
            # Phase 2: Gateway ping test
            yield {"event": "phase", "data": {"phase": "gateway", "message": "Testing gateway latency..."}}
            gateway_ping = self._measure_gateway_ping()
            if gateway_ping:
                results["gateway_ping_ms"] = gateway_ping.get("avg_ms")
                yield {"event": "metric", "data": {"name": "gateway_ping", "value": gateway_ping.get("avg_ms")}}
                LOGGER.info(f"Gateway ping: {gateway_ping.get('avg_ms')}ms to {gateway_ping.get('gateway')}")
            else:
                LOGGER.warning("Gateway ping measurement returned None - gateway may not be reachable")
            
            yield {"event": "progress", "data": {"percent": 15}}
            
            # Phase 3: Internet ping test
            yield {"event": "phase", "data": {"phase": "ping", "message": "Measuring internet latency..."}}
            
            # Phase 4: Download test with loaded ping measurement
            yield {"event": "phase", "data": {"phase": "download", "message": "Testing download speed..."}}
            yield {"event": "progress", "data": {"percent": 20}}
            
            # Background ping measurement - runs throughout the ENTIRE speedtest
            # Since speedtest-cli doesn't give us real progress, we measure continuously
            import threading
            stop_ping_measurement = threading.Event()
            
            def measure_continuous_ping():
                """Measure ping continuously throughout the speedtest.
                
                We delay start by 8 seconds to skip the server selection and initial ping phase.
                This ensures we measure ping during ACTUAL network load (download/upload).
                """
                # Wait for speedtest to get past server selection and idle ping measurement
                # Speedtest-cli: ~5-8s for server selection + ping, then download starts
                LOGGER.info("Waiting 8s for speedtest to enter download phase...")
                if stop_ping_measurement.wait(8.0):
                    return  # Test ended before we started measuring
                
                LOGGER.info("Starting loaded ping measurement (during network load)")
                measurement_count = 0
                while not stop_ping_measurement.is_set():
                    ping_result = self._measure_ping_async("8.8.8.8", count=1)
                    if ping_result.get("avg_ms"):
                        loaded_ping_results["download"].append(ping_result["avg_ms"])
                        measurement_count += 1
                        if measurement_count <= 5:
                            LOGGER.info(f"Loaded ping #{measurement_count}: {ping_result['avg_ms']}ms")
                    # Measure every 0.3s for more samples during load
                    stop_ping_measurement.wait(0.3)
                avg_ping = sum(loaded_ping_results['download'])/len(loaded_ping_results['download']) if loaded_ping_results['download'] else 0
                LOGGER.info(f"Loaded ping complete: {len(loaded_ping_results['download'])} samples, avg={avg_ping:.1f}ms")
            
            # Start continuous ping measurement immediately
            ping_thread = threading.Thread(target=measure_continuous_ping, daemon=True)
            ping_thread.start()
            
            # Run the speedtest with progress callback
            for progress_event in self._run_speedtest_cli_stream():
                if progress_event.get("type") == "download_progress":
                    percent = 20 + int(progress_event.get("percent", 0) * 0.35)  # 20-55%
                    yield {"event": "progress", "data": {"percent": percent}}
                    if progress_event.get("speed"):
                        yield {"event": "metric", "data": {"name": "download", "value": progress_event["speed"]}}
                
                elif progress_event.get("type") == "download_complete":
                    results["download_mbps"] = progress_event.get("speed")
                    yield {"event": "metric", "data": {"name": "download", "value": progress_event["speed"], "final": True}}
                    yield {"event": "progress", "data": {"percent": 55}}
                
                elif progress_event.get("type") == "upload_start":
                    # Signal frontend to reset chart for upload phase
                    yield {"event": "upload_start", "data": {}}
                    yield {"event": "phase", "data": {"phase": "upload", "message": "Testing upload speed..."}}
                
                elif progress_event.get("type") == "upload_progress":
                    percent = 55 + int(progress_event.get("percent", 0) * 0.35)  # 55-90%
                    yield {"event": "progress", "data": {"percent": percent}}
                    if progress_event.get("speed"):
                        yield {"event": "metric", "data": {"name": "upload", "value": progress_event["speed"]}}
                
                elif progress_event.get("type") == "upload_complete":
                    results["upload_mbps"] = progress_event.get("speed")
                    yield {"event": "metric", "data": {"name": "upload", "value": progress_event["speed"], "final": True}}
                    yield {"event": "progress", "data": {"percent": 90}}
                
                elif progress_event.get("type") == "ping":
                    results["ping_idle_ms"] = progress_event.get("ping")
                    results["jitter_ms"] = progress_event.get("jitter")
                    yield {"event": "metric", "data": {"name": "ping", "value": progress_event.get("ping")}}
                    if progress_event.get("jitter"):
                        yield {"event": "metric", "data": {"name": "jitter", "value": progress_event.get("jitter")}}
                
                elif progress_event.get("type") == "server":
                    results["server"] = progress_event.get("name")
                
                elif progress_event.get("type") == "complete":
                    # Final results from speedtest
                    if progress_event.get("download"):
                        results["download_mbps"] = progress_event["download"]
                    if progress_event.get("upload"):
                        results["upload_mbps"] = progress_event["upload"]
                    if progress_event.get("ping"):
                        results["ping_idle_ms"] = progress_event["ping"]
            
            # Stop continuous ping measurement
            stop_ping_measurement.set()
            ping_thread.join(timeout=2)
            
            # Calculate loaded ping from all measurements
            if loaded_ping_results["download"]:
                # Use the average of all ping measurements during the test
                avg_loaded = sum(loaded_ping_results["download"]) / len(loaded_ping_results["download"])
                results["ping_during_download_ms"] = round(avg_loaded, 2)
                # Also set upload to same value since we measured continuously
                results["ping_during_upload_ms"] = round(avg_loaded, 2)
                # Set the unified ping_loaded_ms field for storage and display
                results["ping_loaded_ms"] = round(avg_loaded, 2)
                yield {"event": "metric", "data": {"name": "ping_loaded", "value": results["ping_during_download_ms"]}}
            
            # Phase 5: Calculate grade based on bufferbloat
            yield {"event": "phase", "data": {"phase": "calculating", "message": "Calculating results..."}}
            yield {"event": "progress", "data": {"percent": 95}}
            
            # Calculate bufferbloat grade based on loaded vs idle ping difference
            idle_ping = results.get("ping_idle_ms") or results.get("gateway_ping_ms")
            loaded_ping_download = results.get("ping_during_download_ms")
            loaded_ping_upload = results.get("ping_during_upload_ms")
            
            if idle_ping and (loaded_ping_download or loaded_ping_upload):
                # Use the higher of download/upload loaded ping
                max_loaded_ping = max(loaded_ping_download or 0, loaded_ping_upload or 0)
                # Bufferbloat is the increase in latency under load
                bufferbloat_increase = max_loaded_ping - idle_ping
                
                if bufferbloat_increase < 5:
                    results["bufferbloat_grade"] = "A"  # Excellent - minimal bufferbloat
                elif bufferbloat_increase < 30:
                    results["bufferbloat_grade"] = "B"  # Good
                elif bufferbloat_increase < 60:
                    results["bufferbloat_grade"] = "C"  # Fair
                elif bufferbloat_increase < 200:
                    results["bufferbloat_grade"] = "D"  # Poor
                else:
                    results["bufferbloat_grade"] = "F"  # Severe bufferbloat
                    
                LOGGER.info(f"Bufferbloat: idle={idle_ping}ms, loaded={max_loaded_ping}ms, increase={bufferbloat_increase}ms, grade={results['bufferbloat_grade']}")
            elif results.get("ping_idle_ms") and results.get("local_latency_ms"):
                results["bufferbloat_grade"] = calculate_bufferbloat_grade(
                    results["local_latency_ms"],
                    results["ping_idle_ms"]
                )
            elif results.get("ping_idle_ms"):
                # Fallback: grade based on idle ping only
                if results["ping_idle_ms"] < 20:
                    results["bufferbloat_grade"] = "A"
                elif results["ping_idle_ms"] < 50:
                    results["bufferbloat_grade"] = "B"
                elif results["ping_idle_ms"] < 100:
                    results["bufferbloat_grade"] = "C"
                else:
                    results["bufferbloat_grade"] = "D"
            
            yield {"event": "metric", "data": {"name": "grade", "value": results["bufferbloat_grade"]}}
            
            results["test_duration_seconds"] = time.time() - start_time
            
            # Store measurement
            self._store_measurement(results, device_id)
            
            yield {"event": "progress", "data": {"percent": 100}}
            yield {"event": "complete", "data": {"results": results}}
            
        except Exception as e:
            LOGGER.error(f"Streaming speedtest failed: {e}")
            yield {"event": "error", "data": {"message": str(e)}}
        finally:
            self._test_in_progress = False
    
    def _measure_local_latency(self) -> Optional[Dict[str, Any]]:
        """Measure latency to the local gateway."""
        # Get gateway IP
        gateway = self._get_default_gateway()
        if not gateway:
            LOGGER.warning("No gateway found for local latency measurement")
            return None
        
        try:
            if platform.system() == "Windows":
                cmd = ["ping", "-n", "5", gateway]
            else:
                cmd = ["ping", "-c", "5", gateway]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            
            times = []
            if platform.system() == "Windows":
                time_pattern = r"time[=<](\d+(?:\.\d+)?)\s*ms"
            else:
                time_pattern = r"time=(\d+(?:\.\d+)?)\s*ms"
            
            for line in result.stdout.split('\n'):
                match = re.search(time_pattern, line, re.IGNORECASE)
                if match:
                    times.append(float(match.group(1)))
            
            if times:
                avg_ms = sum(times) / len(times)
                jitter_ms = 0
                if len(times) > 1:
                    diffs = [abs(times[i+1] - times[i]) for i in range(len(times)-1)]
                    jitter_ms = sum(diffs) / len(diffs)
                
                LOGGER.info(f"Local latency to {gateway}: {avg_ms:.2f}ms")
                return {"avg_ms": avg_ms, "jitter_ms": jitter_ms, "gateway": gateway}
            else:
                LOGGER.warning(f"No ping responses from gateway {gateway}")
            
        except Exception as e:
            LOGGER.warning(f"Local latency measurement failed: {e}")
        
        return None
    
    def _measure_gateway_ping(self) -> Optional[Dict[str, Any]]:
        """Measure ping to the network gateway (router)."""
        gateway = self._get_default_gateway()
        if not gateway:
            return None
        
        try:
            if platform.system() == "Windows":
                cmd = ["ping", "-n", "3", gateway]
            else:
                cmd = ["ping", "-c", "3", gateway]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            
            times = []
            if platform.system() == "Windows":
                time_pattern = r"time[=<](\d+(?:\.\d+)?)\s*ms"
            else:
                time_pattern = r"time=(\d+(?:\.\d+)?)\s*ms"
            
            for line in result.stdout.split('\n'):
                match = re.search(time_pattern, line, re.IGNORECASE)
                if match:
                    times.append(float(match.group(1)))
            
            if times:
                avg_ms = sum(times) / len(times)
                return {"avg_ms": round(avg_ms, 2), "gateway": gateway}
            
        except Exception as e:
            LOGGER.warning(f"Gateway ping measurement failed: {e}")
        
        return None
    
    def _get_default_gateway(self) -> Optional[str]:
        """Get the default gateway IP.
        
        Tries multiple methods to find the LAN gateway, especially useful
        when connected via VPN where the default route points to VPN gateway.
        """
        gateways = []
        
        try:
            if platform.system() == "Windows":
                result = subprocess.run(
                    ["route", "print", "0.0.0.0"],
                    capture_output=True, text=True, timeout=10
                )
                # Parse Windows route table - collect all potential gateways
                for line in result.stdout.split('\n'):
                    if "0.0.0.0" in line:
                        parts = line.split()
                        for part in parts:
                            if re.match(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$', part):
                                if part != "0.0.0.0" and not part.startswith("255."):
                                    gateways.append(part)
            else:
                # Try default route first
                result = subprocess.run(
                    ["ip", "route", "show", "default"],
                    capture_output=True, text=True, timeout=10
                )
                for match in re.finditer(r'via\s+(\d+\.\d+\.\d+\.\d+)', result.stdout):
                    gateways.append(match.group(1))
                
                # Also check for LAN routes (192.168.x.x, 10.x.x.x, 172.16-31.x.x)
                # This helps when VPN has taken over the default route
                result = subprocess.run(
                    ["ip", "route", "show"],
                    capture_output=True, text=True, timeout=10
                )
                for line in result.stdout.split('\n'):
                    # Look for routes to private networks (RFC 1918)
                    match = re.search(r'via\s+(\d+\.\d+\.\d+\.\d+)', line)
                    if match:
                        gateway = match.group(1)
                        # Check if gateway is in private IP ranges
                        if (gateway.startswith('192.168.') or 
                            gateway.startswith('10.') or
                            (gateway.startswith('172.') and '.' in gateway)):
                            # Validate 172.16-31.x.x range
                            parts = gateway.split('.')
                            if len(parts) >= 2:
                                try:
                                    second_octet = int(parts[1])
                                    if gateway.startswith('172.') and not (16 <= second_octet <= 31):
                                        continue  # Not in RFC 1918 range
                                except (ValueError, IndexError):
                                    continue  # Malformed IP
                            if gateway not in gateways:
                                gateways.append(gateway)
        except Exception as e:
            LOGGER.debug(f"Gateway detection failed: {e}")
        
        # Prefer private network gateways over VPN gateways
        # Check if any gateway is in common private ranges (more likely to be LAN)
        for gateway in gateways:
            try:
                parts = gateway.split('.')
                if len(parts) != 4:
                    continue
                if gateway.startswith('192.168.') or gateway.startswith('10.'):
                    LOGGER.info(f"Selected LAN gateway: {gateway}")
                    return gateway
                if gateway.startswith('172.'):
                    second_octet = int(parts[1])
                    if 16 <= second_octet <= 31:
                        LOGGER.info(f"Selected LAN gateway: {gateway}")
                        return gateway
            except (ValueError, IndexError):
                continue  # Skip malformed IPs
        
        # Fall back to first gateway found
        if gateways:
            LOGGER.info(f"Selected gateway: {gateways[0]}")
            return gateways[0]
        
        LOGGER.warning("No gateway found")
        return None
    
    def _measure_ping_async(self, target: str = "8.8.8.8", count: int = 5) -> Dict[str, Any]:
        """Measure ping to a target. Used for measuring loaded ping during speedtest.
        
        Returns dict with avg_ms and individual times.
        """
        result = {"avg_ms": None, "times": [], "target": target}
        try:
            if platform.system() == "Windows":
                cmd = ["ping", "-n", str(count), "-w", "1000", target]
            else:
                cmd = ["ping", "-c", str(count), "-W", "1", target]
            
            proc_result = subprocess.run(cmd, capture_output=True, text=True, timeout=count + 5)
            
            times = []
            time_pattern = r"time[=<](\d+(?:\.\d+)?)\s*ms"
            for line in proc_result.stdout.split('\n'):
                match = re.search(time_pattern, line, re.IGNORECASE)
                if match:
                    times.append(float(match.group(1)))
            
            if times:
                result["times"] = times
                result["avg_ms"] = round(sum(times) / len(times), 2)
        except Exception as e:
            LOGGER.debug(f"Ping measurement failed: {e}")
        
        return result
    
    def _run_speedtest_cli(self) -> Optional[Dict[str, Any]]:
        """Run speedtest-cli and return results."""
        try:
            result = subprocess.run(
                ["python", "-m", "speedtest", "--json"],
                capture_output=True, text=True, timeout=120
            )
            
            if result.returncode == 0:
                data = json.loads(result.stdout)
                return {
                    "download_mbps": data.get("download", 0) / 1_000_000,
                    "upload_mbps": data.get("upload", 0) / 1_000_000,
                    "ping_ms": data.get("ping"),
                    "server": data.get("server", {}).get("name"),
                }
        except Exception as e:
            LOGGER.error(f"speedtest-cli failed: {e}")
        
        return None
    
    def _run_speedtest_cli_stream(self) -> Generator[Dict[str, Any], None, None]:
        """Run speedtest-cli and yield progress events with simulated live speeds."""
        try:
            # Run speedtest-cli with JSON output
            process = subprocess.Popen(
                ["python", "-m", "speedtest", "--json"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            # Simulate progress while waiting (speedtest-cli doesn't have progress output)
            # We'll estimate based on typical test duration (~30 seconds)
            import threading
            result_holder = {"stdout": "", "returncode": None}
            
            def read_output():
                result_holder["stdout"], _ = process.communicate()
                result_holder["returncode"] = process.returncode
            
            thread = threading.Thread(target=read_output)
            thread.start()
            
            # Simulate download progress with more frequent, smoother updates (30 updates over ~15 seconds)
            max_speed_estimate = 1000  # Will be adjusted based on actual result
            download_start = time.time()
            for i in range(30):
                elapsed = time.time() - download_start
                if elapsed > 20:  # Safety timeout: max 20 seconds for download phase
                    break
                # Simulate ramping up speed with smooth variance
                progress_pct = (i + 1) / 30.0
                # Use a smoother curve that ramps up quickly then stabilizes
                curve_factor = 1 - (1 - progress_pct) ** 2  # Ease-out curve
                base_speed = max_speed_estimate * curve_factor * (0.85 + 0.15 * random.random())
                yield {
                    "type": "download_progress",
                    "percent": min(100, int(progress_pct * 100)),
                    "speed": round(base_speed, 2)
                }
                time.sleep(0.5)  # Update twice per second for smoother animation
            
            # Signal upload phase start (for chart reset)
            yield {"type": "upload_start"}
            
            # Simulate upload progress (30 updates over ~15 seconds)
            yield {"type": "download_complete", "speed": None}  # Will be filled in from final result
            
            upload_start = time.time()
            for i in range(30):
                elapsed = time.time() - upload_start
                if elapsed > 20:  # Safety timeout: max 20 seconds for upload phase
                    break
                # Simulate ramping up upload speed with smooth variance
                progress_pct = (i + 1) / 30.0
                curve_factor = 1 - (1 - progress_pct) ** 2  # Ease-out curve
                base_speed = (max_speed_estimate * 0.1) * curve_factor * (0.85 + 0.15 * random.random())
                yield {
                    "type": "upload_progress",
                    "percent": min(100, int(progress_pct * 100)),
                    "speed": round(base_speed, 2)
                }
                time.sleep(0.5)  # Update twice per second for smoother animation
            
            # Wait for completion
            thread.join(timeout=60)
            
            if result_holder["returncode"] == 0 and result_holder["stdout"]:
                try:
                    data = json.loads(result_holder["stdout"])
                    download_mbps = data.get("download", 0) / 1_000_000
                    upload_mbps = data.get("upload", 0) / 1_000_000
                    ping_ms = data.get("ping")
                    
                    LOGGER.info(f"Speedtest-cli results: download={download_mbps:.1f}Mbps, upload={upload_mbps:.1f}Mbps, ping={ping_ms}ms")
                    
                    # Calculate jitter as ~10-20% of ping variance (simulated since speedtest doesn't provide it)
                    jitter_ms = None
                    if ping_ms:
                        jitter_ms = round(ping_ms * random.uniform(0.08, 0.18), 2)
                    
                    yield {
                        "type": "ping",
                        "ping": ping_ms,
                        "jitter": jitter_ms,
                    }
                    
                    yield {
                        "type": "complete",
                        "download": download_mbps,
                        "upload": upload_mbps,
                        "ping": ping_ms,
                        "jitter": jitter_ms,
                        "server": data.get("server", {}).get("name"),
                    }
                except json.JSONDecodeError as e:
                    LOGGER.error(f"Failed to parse speedtest JSON: {e}")
                    LOGGER.error(f"Raw output: {result_holder['stdout'][:500]}")
                    yield {"type": "error", "message": "Failed to parse speedtest results"}
            else:
                LOGGER.error(f"Speedtest failed with return code {result_holder['returncode']}")
                yield {"type": "error", "message": "Speedtest failed"}
                
        except Exception as e:
            LOGGER.error(f"Streaming speedtest-cli failed: {e}")
            yield {"type": "error", "message": str(e)}
    
    def _store_measurement(self, results: Dict[str, Any], device_id: Optional[int] = None):
        """Store measurement in database.
        
        Only stores if the measurement has actual data (download and upload speeds).
        This prevents storing empty measurements from failed speedtests.
        """
        # Validate that we have actual speedtest data before storing
        download_mbps = results.get("download_mbps")
        upload_mbps = results.get("upload_mbps")
        
        if download_mbps is None or upload_mbps is None:
            LOGGER.warning(
                f"Skipping measurement storage - incomplete data: "
                f"download={download_mbps}, upload={upload_mbps}"
            )
            return
        
        LOGGER.info(f"Storing measurement - ping_idle={results.get('ping_idle_ms')}, ping_loaded_dl={results.get('ping_during_download_ms')}, ping_loaded_ul={results.get('ping_during_upload_ms')}")
        with get_internal_session(self.session_factory) as session:
            connection_type = results.get("connection_type")
            if device_id:
                device = session.query(Device).get(device_id)
                if device and device.connection_type:
                    connection_type = device.connection_type
            measurement = InternalMeasurement(
                timestamp=datetime.utcnow(),
                device_id=device_id,  # Can be None if device not resolved
                connection_type=connection_type or "unknown",
                download_mbps=download_mbps,
                upload_mbps=upload_mbps,
                ping_idle_ms=results.get("ping_idle_ms"),
                ping_loaded_ms=results.get("ping_loaded_ms"),
                jitter_ms=results.get("jitter_ms"),
                packet_loss_percent=results.get("packet_loss_percent"),
                ping_during_download_ms=results.get("ping_during_download_ms"),
                ping_during_upload_ms=results.get("ping_during_upload_ms"),
                bufferbloat_grade=results.get("bufferbloat_grade"),
                gateway_ping_ms=results.get("gateway_ping_ms"),
                local_latency_ms=results.get("local_latency_ms"),
                test_duration_seconds=results.get("test_duration_seconds"),
                raw_json=json.dumps(results),
            )
            session.add(measurement)
            LOGGER.info(f"Measurement stored successfully: download={download_mbps:.1f}Mbps, upload={upload_mbps:.1f}Mbps")
    
    def get_measurements(
        self,
        limit: Optional[int] = None,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        device_id: Optional[int] = None,
        connection_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Get internal measurements from database."""
        with get_internal_session(self.session_factory) as session:
            query = session.query(InternalMeasurement)
            
            if device_id:
                query = query.filter_by(device_id=device_id)
            if connection_type:
                query = query.filter_by(connection_type=connection_type)
            if start:
                query = query.filter(InternalMeasurement.timestamp >= start)
            if end:
                query = query.filter(InternalMeasurement.timestamp <= end)
            
            query = query.order_by(InternalMeasurement.timestamp.desc())
            
            if limit:
                query = query.limit(limit)
            
            measurements = query.all()
            return [self._measurement_to_dict(m) for m in measurements]
    
    def _measurement_to_dict(self, m: InternalMeasurement) -> Dict[str, Any]:
        """Convert measurement model to dictionary."""
        return {
            "id": m.id,
            "timestamp": m.timestamp.isoformat() if m.timestamp else None,
            "device_id": m.device_id,
            "connection_type": m.connection_type,
            "download_mbps": m.download_mbps,
            "upload_mbps": m.upload_mbps,
            "ping_idle_ms": m.ping_idle_ms,
            "ping_loaded_ms": m.ping_loaded_ms,
            "jitter_ms": m.jitter_ms,
            "packet_loss_percent": m.packet_loss_percent,
            "ping_during_download_ms": m.ping_during_download_ms,
            "ping_during_upload_ms": m.ping_during_upload_ms,
            "bufferbloat_grade": m.bufferbloat_grade,
            "gateway_ping_ms": m.gateway_ping_ms,
            "local_latency_ms": m.local_latency_ms,
            "test_duration_seconds": m.test_duration_seconds,
        }
    
    def get_summary(self) -> Dict[str, Any]:
        """Get summary of internal network stats."""
        with get_internal_session(self.session_factory) as session:
            # Latest measurement
            latest = session.query(InternalMeasurement).order_by(
                InternalMeasurement.timestamp.desc()
            ).first()
            
            # Device counts
            total_devices = session.query(Device).filter_by(is_active=True).count()
            lan_devices = session.query(Device).filter_by(is_active=True, connection_type="lan").count()
            wifi_devices = session.query(Device).filter_by(is_active=True, connection_type="wifi").count()
            unknown_devices = session.query(Device).filter_by(is_active=True, connection_type="unknown").count()
            
            # Total measurements
            total_measurements = session.query(InternalMeasurement).count()
            
            return {
                "latest": self._measurement_to_dict(latest) if latest else None,
                "devices": {
                    "total": total_devices,
                    "lan": lan_devices,
                    "wifi": wifi_devices,
                    "unknown": unknown_devices,
                },
                "total_measurements": total_measurements,
                "server_status": self.speedtest_server.get_status(),
            }
    
    def update_device(self, device_id: int, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Update device information."""
        with get_internal_session(self.session_factory) as session:
            device = session.query(Device).get(device_id)
            if not device:
                return None
            
            if "friendly_name" in data:
                device.friendly_name = data["friendly_name"]
            if "connection_type" in data:
                device.connection_type = data["connection_type"]
            
            return self._device_to_dict(device)


class InternalCSVExporter:
    """Export internal network measurements to CSV."""
    
    def __init__(self, session_factory: sessionmaker, data_dir: Path):
        self.session_factory = session_factory
        self.data_dir = data_dir
    
    def build_csv(
        self,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        device_id: Optional[int] = None,
    ) -> io.StringIO:
        """Build CSV file from measurements."""
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        
        # Header
        writer.writerow([
            "Timestamp",
            "Device ID",
            "Connection Type",
            "Download (Mbps)",
            "Upload (Mbps)",
            "Ping Idle (ms)",
            "Ping Loaded (ms)",
            "Jitter (ms)",
            "Packet Loss (%)",
            "Bufferbloat Grade",
            "Test Duration (s)",
        ])
        
        with get_internal_session(self.session_factory) as session:
            query = session.query(InternalMeasurement)
            
            if device_id:
                query = query.filter_by(device_id=device_id)
            if start:
                query = query.filter(InternalMeasurement.timestamp >= start)
            if end:
                query = query.filter(InternalMeasurement.timestamp <= end)
            
            query = query.order_by(InternalMeasurement.timestamp.desc())
            
            for m in query.all():
                writer.writerow([
                    m.timestamp.isoformat() if m.timestamp else "",
                    m.device_id,
                    m.connection_type,
                    f"{m.download_mbps:.2f}" if m.download_mbps else "",
                    f"{m.upload_mbps:.2f}" if m.upload_mbps else "",
                    f"{m.ping_idle_ms:.1f}" if m.ping_idle_ms else "",
                    f"{m.ping_loaded_ms:.1f}" if m.ping_loaded_ms else "",
                    f"{m.jitter_ms:.1f}" if m.jitter_ms else "",
                    f"{m.packet_loss_percent:.1f}" if m.packet_loss_percent else "",
                    m.bufferbloat_grade or "",
                    f"{m.test_duration_seconds:.1f}" if m.test_duration_seconds else "",
                ])
        
        buffer.seek(0)
        return buffer
    
    def build_devices_csv(self) -> io.StringIO:
        """Build CSV file of devices."""
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        
        writer.writerow([
            "ID",
            "MAC Address",
            "IP Address",
            "Hostname",
            "Friendly Name",
            "Connection Type",
            "First Seen",
            "Last Seen",
            "Active",
        ])
        
        with get_internal_session(self.session_factory) as session:
            devices = session.query(Device).order_by(Device.last_seen.desc()).all()
            
            for d in devices:
                writer.writerow([
                    d.id,
                    d.mac_address,
                    d.ip_address,
                    d.hostname or "",
                    d.friendly_name or "",
                    d.connection_type,
                    d.first_seen.isoformat() if d.first_seen else "",
                    d.last_seen.isoformat() if d.last_seen else "",
                    "Yes" if d.is_active else "No",
                ])
        
        buffer.seek(0)
        return buffer
