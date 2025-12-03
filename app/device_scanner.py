"""Network device discovery and classification."""

from __future__ import annotations

import logging
import platform
import re
import socket
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
import json

LOGGER = logging.getLogger(__name__)


@dataclass
class NetworkDevice:
    """Represents a discovered network device."""
    ip_address: str
    mac_address: str = ""
    hostname: str = ""
    friendly_name: str = ""
    connection_type: str = "unknown"  # 'lan', 'wifi', 'unknown'
    ping_ms: Optional[float] = None
    ping_jitter_ms: Optional[float] = None  # Variance in ping times
    is_online: bool = True
    vendor: str = ""
    last_seen: datetime = field(default_factory=datetime.utcnow)
    is_local: bool = False  # Is this the machine running the server
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "ip_address": self.ip_address,
            "mac_address": self.mac_address,
            "hostname": self.hostname,
            "friendly_name": self.friendly_name or self.hostname or self.ip_address,
            "connection_type": self.connection_type,
            "ping_ms": self.ping_ms,
            "ping_jitter_ms": self.ping_jitter_ms,
            "is_online": self.is_online,
            "vendor": self.vendor,
            "last_seen": self.last_seen.isoformat(),
            "is_local": self.is_local,
        }


class DeviceScanner:
    """
    Scans the local network for devices and classifies them.
    Uses multiple ping measurements and jitter analysis to distinguish LAN vs WiFi.
    """
    
    # Common MAC address OUI prefixes for known WiFi-only vendors
    WIFI_VENDOR_PREFIXES = {
        # Apple mobile devices
        "00:1C:B3", "00:21:E9", "00:25:BC", "00:26:08", "00:26:B0", "00:26:BB",
        "04:0C:CE", "04:15:52", "04:26:65", "04:52:F3", "04:54:53", "04:DB:56",
        "10:93:E9", "10:9A:DD", "14:5A:05", "18:E7:F4", "1C:1A:C0", "1C:36:BB",
        # Common WiFi chipset vendors
        "00:0C:43",  # Ralink
        "00:17:9A",  # D-Link WiFi
        "00:1A:2B",  # Cisco/Linksys WiFi
    }
    
    # Keywords suggesting WiFi devices
    WIFI_HOSTNAME_KEYWORDS = [
        "phone", "ipad", "iphone", "android", "tablet", "mobile",
        "galaxy", "pixel", "oneplus", "xiaomi", "huawei", "oppo",
        "laptop", "macbook", "surface", "chromebook"
    ]
    
    # Keywords suggesting wired LAN devices
    LAN_HOSTNAME_KEYWORDS = [
        "nas", "server", "switch", "router", "gateway", "printer",
        "desktop", "workstation", "pc-", "-pc", "tower"
    ]
    
    def __init__(self, network_prefix: Optional[str] = None):
        """
        Initialize device scanner.
        
        Args:
            network_prefix: Network prefix like "192.168.0" or auto-detect if None
        """
        self._network_prefix = network_prefix
        self._devices: Dict[str, NetworkDevice] = {}
        self._lock = threading.Lock()
        self._arp_cache: Dict[str, str] = {}  # IP -> MAC mapping
        self._local_ip: Optional[str] = None
        self._local_mac: Optional[str] = None
        
    def _get_local_ip(self) -> str:
        """Get local IP address."""
        if self._local_ip:
            return self._local_ip
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            self._local_ip = s.getsockname()[0]
            s.close()
            return self._local_ip
        except Exception:
            return "127.0.0.1"
    
    def _get_local_mac(self) -> str:
        """Get MAC address of local machine."""
        if self._local_mac:
            return self._local_mac
        
        try:
            local_ip = self._get_local_ip()
            if platform.system() == "Windows":
                result = subprocess.run(["getmac", "/v", "/fo", "csv"], capture_output=True, text=True, timeout=10)
                # Find the adapter with our local IP
                for line in result.stdout.split('\n'):
                    if 'Ethernet' in line or 'Wi-Fi' in line or 'Wireless' in line:
                        match = re.search(r'([\dA-F]{2}-[\dA-F]{2}-[\dA-F]{2}-[\dA-F]{2}-[\dA-F]{2}-[\dA-F]{2})', line, re.IGNORECASE)
                        if match:
                            self._local_mac = match.group(1).upper().replace("-", ":")
                            return self._local_mac
                
                # Fallback: use ipconfig
                result = subprocess.run(["ipconfig", "/all"], capture_output=True, text=True, timeout=10)
                found_adapter = False
                for line in result.stdout.split('\n'):
                    if local_ip in line:
                        found_adapter = True
                    if found_adapter:
                        match = re.search(r'Physical Address.*?:\s*([\dA-F]{2}-[\dA-F]{2}-[\dA-F]{2}-[\dA-F]{2}-[\dA-F]{2}-[\dA-F]{2})', line, re.IGNORECASE)
                        if match:
                            self._local_mac = match.group(1).upper().replace("-", ":")
                            return self._local_mac
            else:
                # Linux/macOS
                result = subprocess.run(["ip", "addr"], capture_output=True, text=True, timeout=10)
                lines = result.stdout.split('\n')
                for i, line in enumerate(lines):
                    if local_ip in line:
                        # Look back for MAC
                        for j in range(i, max(0, i-5), -1):
                            match = re.search(r'link/ether\s+([\da-f:]+)', lines[j], re.IGNORECASE)
                            if match:
                                self._local_mac = match.group(1).upper()
                                return self._local_mac
        except Exception as e:
            LOGGER.warning(f"Failed to get local MAC: {e}")
        
        return ""
    
    def _is_local_connection_wired(self) -> bool:
        """Detect if the local machine is connected via Ethernet or WiFi."""
        try:
            if platform.system() == "Windows":
                # Check active network adapter type
                result = subprocess.run(
                    ["netsh", "interface", "show", "interface"],
                    capture_output=True, text=True, timeout=10
                )
                lines = result.stdout.lower().split('\n')
                for line in lines:
                    if 'connected' in line:
                        if 'ethernet' in line or 'local area' in line:
                            return True
                        if 'wi-fi' in line or 'wireless' in line or 'wlan' in line:
                            return False
                
                # Alternative: check via PowerShell
                result = subprocess.run(
                    ["powershell", "-Command", "Get-NetAdapter | Where-Object Status -eq 'Up' | Select-Object -ExpandProperty InterfaceDescription"],
                    capture_output=True, text=True, timeout=10
                )
                output = result.stdout.lower()
                if 'ethernet' in output or 'realtek' in output or 'intel.*ethernet' in output:
                    return True
                if 'wi-fi' in output or 'wireless' in output or '802.11' in output:
                    return False
            else:
                # Linux: check if using eth/enp interface
                result = subprocess.run(["ip", "route", "get", "8.8.8.8"], capture_output=True, text=True, timeout=10)
                if 'eth' in result.stdout or 'enp' in result.stdout or 'eno' in result.stdout:
                    return True
                if 'wlan' in result.stdout or 'wlp' in result.stdout:
                    return False
        except Exception as e:
            LOGGER.warning(f"Failed to detect local connection type: {e}")
        
        return True  # Default to LAN
        
    def _get_network_prefix(self) -> str:
        """Get network prefix from local IP."""
        if self._network_prefix:
            return self._network_prefix
        
        local_ip = self._get_local_ip()
        return ".".join(local_ip.split(".")[:3])
    
    def _ping_host_multiple(self, ip: str, count: int = 4, timeout: int = 1) -> Tuple[Optional[float], Optional[float]]:
        """
        Ping a host multiple times and return (avg_ms, jitter_ms).
        Jitter helps distinguish LAN (low jitter) from WiFi (higher jitter).
        """
        try:
            if platform.system() == "Windows":
                cmd = ["ping", "-n", str(count), "-w", str(timeout * 1000), ip]
            else:
                cmd = ["ping", "-c", str(count), "-W", str(timeout), ip]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=(timeout + 2) * count)
            
            if result.returncode == 0:
                # Parse all ping times
                times = []
                if platform.system() == "Windows":
                    for match in re.finditer(r"time[=<](\d+(?:\.\d+)?)", result.stdout, re.IGNORECASE):
                        times.append(float(match.group(1)))
                else:
                    for match in re.finditer(r"time=(\d+(?:\.\d+)?)", result.stdout, re.IGNORECASE):
                        times.append(float(match.group(1)))
                
                if times:
                    avg_ms = sum(times) / len(times)
                    # Calculate jitter (average difference between consecutive pings)
                    if len(times) > 1:
                        diffs = [abs(times[i+1] - times[i]) for i in range(len(times)-1)]
                        jitter_ms = sum(diffs) / len(diffs)
                    else:
                        jitter_ms = 0
                    return avg_ms, jitter_ms
            return None, None
        except Exception:
            return None, None
    
    def _ping_host(self, ip: str, timeout: int = 1) -> Optional[float]:
        """Ping a host once and return response time in ms."""
        avg, _ = self._ping_host_multiple(ip, count=1, timeout=timeout)
        return avg
    
    def _get_arp_table(self) -> Dict[str, str]:
        """Get ARP table (IP -> MAC mapping)."""
        arp_cache = {}
        try:
            if platform.system() == "Windows":
                result = subprocess.run(["arp", "-a"], capture_output=True, text=True, timeout=10)
                # Parse Windows ARP output
                for line in result.stdout.split('\n'):
                    match = re.search(r"(\d+\.\d+\.\d+\.\d+)\s+([\da-f]{2}[:-][\da-f]{2}[:-][\da-f]{2}[:-][\da-f]{2}[:-][\da-f]{2}[:-][\da-f]{2})", line, re.IGNORECASE)
                    if match:
                        ip = match.group(1)
                        mac = match.group(2).upper().replace("-", ":")
                        arp_cache[ip] = mac
            else:
                result = subprocess.run(["arp", "-n"], capture_output=True, text=True, timeout=10)
                # Parse Linux/macOS ARP output
                for line in result.stdout.split('\n'):
                    parts = line.split()
                    if len(parts) >= 3:
                        ip = parts[0]
                        mac_candidate = parts[2] if len(parts) > 2 else parts[1]
                        if re.match(r"[\da-f]{2}:[\da-f]{2}:[\da-f]{2}:[\da-f]{2}:[\da-f]{2}:[\da-f]{2}", mac_candidate, re.IGNORECASE):
                            arp_cache[ip] = mac_candidate.upper()
        except Exception as e:
            LOGGER.warning(f"Failed to get ARP table: {e}")
        
        return arp_cache
    
    def _resolve_hostname(self, ip: str) -> str:
        """Try to resolve hostname for an IP address."""
        try:
            hostname = socket.gethostbyaddr(ip)[0]
            return hostname
        except (socket.herror, socket.gaierror):
            return ""
    
    def _classify_connection_type(self, device: NetworkDevice) -> str:
        """
        Classify device as LAN or WiFi based on multiple heuristics.
        
        Uses:
        1. Ping latency AND jitter (most reliable indicator)
        2. Hostname keywords
        3. MAC vendor prefixes (least reliable)
        
        LAN characteristics: Low latency (<3ms typically), very low jitter (<0.5ms)
        WiFi characteristics: Higher latency (3-15ms), higher jitter (>1ms)
        """
        score = 0  # Positive = LAN, Negative = WiFi
        
        # Local machine - detect actual interface
        if device.is_local:
            return "lan" if self._is_local_connection_wired() else "wifi"
        
        # 1. Analyze ping latency and jitter (most reliable)
        if device.ping_ms is not None:
            # Ping latency analysis
            if device.ping_ms < 2:
                score += 3  # Very likely LAN
            elif device.ping_ms < 5:
                score += 1  # Probably LAN
            elif device.ping_ms > 10:
                score -= 2  # Likely WiFi
            elif device.ping_ms > 20:
                score -= 3  # Very likely WiFi
            
            # Jitter analysis (WiFi has more jitter)
            if device.ping_jitter_ms is not None:
                if device.ping_jitter_ms < 0.3:
                    score += 2  # Very stable = LAN
                elif device.ping_jitter_ms < 1:
                    score += 1  # Stable = probably LAN
                elif device.ping_jitter_ms > 2:
                    score -= 2  # Unstable = likely WiFi
                elif device.ping_jitter_ms > 5:
                    score -= 3  # Very unstable = very likely WiFi
        
        # 2. Hostname keywords
        hostname_lower = device.hostname.lower()
        for keyword in self.WIFI_HOSTNAME_KEYWORDS:
            if keyword in hostname_lower:
                score -= 2
                break
        for keyword in self.LAN_HOSTNAME_KEYWORDS:
            if keyword in hostname_lower:
                score += 2
                break
        
        # 3. MAC vendor prefix (less reliable, use as tiebreaker)
        if device.mac_address:
            prefix = device.mac_address[:8]
            if prefix in self.WIFI_VENDOR_PREFIXES:
                score -= 1
        
        # Determine type based on score
        if score >= 2:
            return "lan"
        elif score <= -2:
            return "wifi"
        else:
            # Uncertain - default based on ping if available
            if device.ping_ms is not None:
                return "lan" if device.ping_ms < 5 else "wifi"
            return "unknown"
    
    def scan_network(self, ip_range: Optional[List[int]] = None) -> List[NetworkDevice]:
        """
        Scan network for devices with detailed ping analysis.
        
        Args:
            ip_range: Range of IP addresses to scan (e.g., [1, 254])
        
        Returns:
            List of discovered devices
        """
        if ip_range is None:
            ip_range = [1, 254]
        
        network_prefix = self._get_network_prefix()
        local_ip = self._get_local_ip()
        
        # First, get ARP table for MAC addresses
        self._arp_cache = self._get_arp_table()
        
        devices = []
        
        # Add local machine first
        local_device = self._create_local_device()
        if local_device:
            devices.append(local_device)
        
        # Parallel ping scan with multiple pings for jitter analysis
        with ThreadPoolExecutor(max_workers=30) as executor:
            futures = {}
            for i in range(ip_range[0], ip_range[1] + 1):
                ip = f"{network_prefix}.{i}"
                if ip == local_ip:
                    continue  # Skip local, already added
                futures[executor.submit(self._ping_host_multiple, ip, 3)] = ip
            
            for future in as_completed(futures):
                ip = futures[future]
                try:
                    ping_ms, jitter_ms = future.result()
                    if ping_ms is not None:
                        mac = self._arp_cache.get(ip, "")
                        hostname = self._resolve_hostname(ip)
                        
                        device = NetworkDevice(
                            ip_address=ip,
                            mac_address=mac,
                            hostname=hostname,
                            ping_ms=round(ping_ms, 2),
                            ping_jitter_ms=round(jitter_ms, 2) if jitter_ms else None,
                            is_online=True,
                        )
                        device.connection_type = self._classify_connection_type(device)
                        devices.append(device)
                        
                        LOGGER.debug(f"Found device: {ip} ({hostname or 'unknown'}) - {device.connection_type} "
                                    f"(ping={ping_ms:.1f}ms, jitter={jitter_ms:.1f}ms)")
                except Exception as e:
                    LOGGER.debug(f"Error scanning {ip}: {e}")
        
        with self._lock:
            for device in devices:
                self._devices[device.ip_address] = device
        
        LOGGER.info(f"Network scan complete. Found {len(devices)} devices.")
        return devices
    
    def _create_local_device(self) -> Optional[NetworkDevice]:
        """Create a device entry for the local machine."""
        try:
            local_ip = self._get_local_ip()
            local_mac = self._get_local_mac()
            hostname = socket.gethostname()
            
            device = NetworkDevice(
                ip_address=local_ip,
                mac_address=local_mac,
                hostname=hostname,
                ping_ms=0.1,  # Local is essentially instant
                ping_jitter_ms=0,
                is_online=True,
                is_local=True,
            )
            device.connection_type = self._classify_connection_type(device)
            return device
        except Exception as e:
            LOGGER.warning(f"Failed to create local device entry: {e}")
            return None
    
    def quick_scan(self) -> List[NetworkDevice]:
        """
        Quick scan using ARP cache + ping analysis.
        Faster than full network scan but includes jitter measurement.
        """
        self._arp_cache = self._get_arp_table()
        local_ip = self._get_local_ip()
        devices = []
        
        # Add local machine first
        local_device = self._create_local_device()
        if local_device:
            devices.append(local_device)
        
        # Ping devices in ARP cache with multiple pings
        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = {}
            for ip, mac in self._arp_cache.items():
                if ip == local_ip:
                    continue
                futures[executor.submit(self._ping_host_multiple, ip, 3)] = (ip, mac)
            
            for future in as_completed(futures):
                ip, mac = futures[future]
                try:
                    ping_ms, jitter_ms = future.result()
                    if ping_ms is not None:
                        hostname = self._resolve_hostname(ip)
                        device = NetworkDevice(
                            ip_address=ip,
                            mac_address=mac,
                            hostname=hostname,
                            ping_ms=round(ping_ms, 2),
                            ping_jitter_ms=round(jitter_ms, 2) if jitter_ms else None,
                            is_online=True,
                        )
                        device.connection_type = self._classify_connection_type(device)
                        devices.append(device)
                except Exception as e:
                    LOGGER.debug(f"Error pinging {ip}: {e}")
        
        with self._lock:
            for device in devices:
                self._devices[device.ip_address] = device
        
        return devices
    
    def get_device(self, ip: str) -> Optional[NetworkDevice]:
        """Get device by IP address."""
        with self._lock:
            return self._devices.get(ip)
    
    def get_all_devices(self) -> List[NetworkDevice]:
        """Get all discovered devices."""
        with self._lock:
            return list(self._devices.values())
    
    def get_lan_devices(self) -> List[NetworkDevice]:
        """Get devices classified as LAN (wired)."""
        with self._lock:
            return [d for d in self._devices.values() if d.connection_type == "lan"]
    
    def get_wifi_devices(self) -> List[NetworkDevice]:
        """Get devices classified as WiFi."""
        with self._lock:
            return [d for d in self._devices.values() if d.connection_type == "wifi"]
    
    def refresh_device(self, ip: str) -> Optional[NetworkDevice]:
        """Refresh status of a specific device with detailed ping analysis."""
        ping_ms, jitter_ms = self._ping_host_multiple(ip, count=3)
        
        with self._lock:
            device = self._devices.get(ip)
            if device:
                device.ping_ms = round(ping_ms, 2) if ping_ms else None
                device.ping_jitter_ms = round(jitter_ms, 2) if jitter_ms else None
                device.is_online = ping_ms is not None
                device.last_seen = datetime.utcnow() if ping_ms else device.last_seen
                device.connection_type = self._classify_connection_type(device)
                return device
        
        return None


# Singleton instance
_scanner: Optional[DeviceScanner] = None


def get_device_scanner() -> DeviceScanner:
    """Get or create singleton DeviceScanner instance."""
    global _scanner
    if _scanner is None:
        _scanner = DeviceScanner()
    return _scanner
