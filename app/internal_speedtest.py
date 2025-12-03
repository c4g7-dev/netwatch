"""Internal network speedtest server and device testing functionality.

Pure Python implementation - no external dependencies like iperf3 required.
"""

from __future__ import annotations

import logging
import platform
import re
import socket
import struct
import subprocess
import threading
import time
from datetime import datetime
from typing import Optional, Dict, Any

LOGGER = logging.getLogger(__name__)


class InternalSpeedtestServer:
    """
    Pure Python internal speedtest server.
    Provides bandwidth testing for local network devices without external dependencies.
    
    Protocol:
    - Client connects to TCP port 5201
    - Client sends command: "DOWNLOAD <bytes>" or "UPLOAD <bytes>"
    - For DOWNLOAD: Server sends random data, client measures speed
    - For UPLOAD: Client sends data, server measures and returns speed
    """
    
    CHUNK_SIZE = 65536  # 64KB chunks for transfer
    HEADER_FORMAT = "!Q"  # Network byte order, unsigned long long (8 bytes)
    
    def __init__(self, port: int = 5201, bind_address: str = "0.0.0.0"):
        self.port = port
        self.bind_address = bind_address
        self._server_socket: Optional[socket.socket] = None
        self._running = False
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._total_tests = 0
        self._start_time: Optional[datetime] = None
        # Pre-generate random data for speed tests (more varied pattern)
        self._random_chunk = bytes([(i * 17 + 31) % 256 for i in range(self.CHUNK_SIZE)])
        
    @property
    def is_running(self) -> bool:
        """Check if server is running."""
        with self._lock:
            return self._running and self._server_socket is not None
    
    @property
    def uptime_seconds(self) -> float:
        """Get server uptime in seconds."""
        if self._start_time is None or not self.is_running:
            return 0.0
        return (datetime.utcnow() - self._start_time).total_seconds()
    
    def _handle_client(self, client_socket: socket.socket, address: tuple):
        """Handle a single client connection."""
        try:
            client_socket.settimeout(30)  # 30 second timeout
            
            # Receive command (first line)
            data = b""
            while b"\n" not in data and len(data) < 1024:
                chunk = client_socket.recv(1024)
                if not chunk:
                    return
                data += chunk
            
            command_line = data.split(b"\n")[0].decode("utf-8").strip()
            parts = command_line.split()
            
            if not parts:
                client_socket.send(b"ERROR: Empty command\n")
                return
            
            cmd = parts[0].upper()
            
            if cmd == "PING":
                # Simple ping response
                client_socket.send(b"PONG\n")
                
            elif cmd == "DOWNLOAD":
                # Client wants to download data from server
                bytes_to_send = int(parts[1]) if len(parts) > 1 else 10 * 1024 * 1024  # Default 10MB
                self._handle_download(client_socket, bytes_to_send)
                self._total_tests += 1
                
            elif cmd == "UPLOAD":
                # Client wants to upload data to server
                bytes_to_receive = int(parts[1]) if len(parts) > 1 else 10 * 1024 * 1024  # Default 10MB
                self._handle_upload(client_socket, bytes_to_receive, data[len(command_line) + 1:])
                self._total_tests += 1
                
            elif cmd == "STATUS":
                # Return server status
                status = f"OK uptime={self.uptime_seconds:.1f} tests={self._total_tests}\n"
                client_socket.send(status.encode())
                
            else:
                client_socket.send(f"ERROR: Unknown command '{cmd}'\n".encode())
                
        except socket.timeout:
            LOGGER.debug(f"Client {address} timed out")
        except Exception as e:
            LOGGER.error(f"Error handling client {address}: {e}")
        finally:
            try:
                client_socket.close()
            except Exception:
                pass
    
    def _handle_download(self, client_socket: socket.socket, total_bytes: int):
        """Send data to client for download speed test."""
        # Send header: total bytes we'll send
        header = struct.pack(self.HEADER_FORMAT, total_bytes)
        client_socket.sendall(header)
        
        # Send data in chunks
        bytes_sent = 0
        while bytes_sent < total_bytes:
            chunk_size = min(self.CHUNK_SIZE, total_bytes - bytes_sent)
            client_socket.sendall(self._random_chunk[:chunk_size])
            bytes_sent += chunk_size
        
        LOGGER.debug(f"Download test: sent {bytes_sent:,} bytes")
    
    def _handle_upload(self, client_socket: socket.socket, total_bytes: int, initial_data: bytes):
        """Receive data from client for upload speed test."""
        # Send acknowledgment
        client_socket.send(b"READY\n")
        
        # Receive data
        bytes_received = len(initial_data)
        start_time = time.perf_counter()
        
        while bytes_received < total_bytes:
            try:
                chunk = client_socket.recv(self.CHUNK_SIZE)
                if not chunk:
                    break
                bytes_received += len(chunk)
            except socket.timeout:
                break
        
        elapsed = time.perf_counter() - start_time
        speed_mbps = (bytes_received * 8) / (elapsed * 1_000_000) if elapsed > 0 else 0
        
        # Send result
        result = f"DONE bytes={bytes_received} time={elapsed:.3f} speed_mbps={speed_mbps:.2f}\n"
        client_socket.send(result.encode())
        
        LOGGER.debug(f"Upload test: received {bytes_received:,} bytes in {elapsed:.2f}s ({speed_mbps:.2f} Mbps)")
    
    def _server_loop(self):
        """Main server loop accepting connections."""
        LOGGER.info(f"Speedtest server listening on {self.bind_address}:{self.port}")
        
        while self._running:
            try:
                self._server_socket.settimeout(1.0)  # Check running flag every second
                try:
                    client_socket, address = self._server_socket.accept()
                    LOGGER.debug(f"New connection from {address}")
                    # Handle each client in a separate thread
                    client_thread = threading.Thread(
                        target=self._handle_client,
                        args=(client_socket, address),
                        daemon=True
                    )
                    client_thread.start()
                except socket.timeout:
                    continue
            except Exception as e:
                if self._running:
                    LOGGER.error(f"Server loop error: {e}")
                break
        
        LOGGER.info("Speedtest server loop ended")
    
    def start(self) -> bool:
        """Start the speedtest server."""
        with self._lock:
            if self._running:
                LOGGER.warning("Internal speedtest server already running")
                return True
            
            try:
                self._server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self._server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                self._server_socket.bind((self.bind_address, self.port))
                self._server_socket.listen(5)
                
                self._running = True
                self._start_time = datetime.utcnow()
                
                # Start server thread
                self._thread = threading.Thread(target=self._server_loop, daemon=True)
                self._thread.start()
                
                LOGGER.info(f"Internal speedtest server started on port {self.port}")
                return True
                
            except OSError as e:
                import errno
                if e.errno in (10048, errno.EADDRINUSE):  # Windows: 10048, Linux: 98
                    LOGGER.error(f"Port {self.port} is already in use")
                elif e.errno == errno.EACCES:  # Permission denied (Linux)
                    LOGGER.error(f"Permission denied when trying to bind to port {self.port}")
                else:
                    LOGGER.error(f"Failed to start server: {e}")
                self._server_socket = None
                return False
            except Exception as e:
                LOGGER.error(f"Error starting internal speedtest server: {e}")
                self._server_socket = None
                return False
    
    def stop(self) -> bool:
        """Stop the speedtest server."""
        with self._lock:
            if not self._running:
                return True
            
            self._running = False
            
            if self._server_socket:
                try:
                    self._server_socket.close()
                except Exception:
                    pass
                self._server_socket = None
            
            if self._thread and self._thread.is_alive():
                self._thread.join(timeout=2.0)
            
            self._start_time = None
            LOGGER.info("Internal speedtest server stopped")
            return True
    
    def get_status(self) -> Dict[str, Any]:
        """Get server status information."""
        return {
            "running": self.is_running,
            "port": self.port,
            "bind_address": self.bind_address,
            "uptime_seconds": self.uptime_seconds,
            "total_tests": self._total_tests,
        }


class InternalSpeedtest:
    """
    Run internal network speedtest from client to server.
    Uses pure Python socket implementation.
    """
    
    CHUNK_SIZE = 65536
    HEADER_FORMAT = "!Q"
    
    def __init__(self, server_host: str = "localhost", server_port: int = 5201):
        self.server_host = server_host
        self.server_port = server_port
    
    def _connect(self) -> socket.socket:
        """Create connection to server."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(30)
        sock.connect((self.server_host, self.server_port))
        return sock
    
    def run_download_test(self, test_bytes: int = 10 * 1024 * 1024) -> Dict[str, Any]:
        """Run download speed test (server sends to client)."""
        sock = self._connect()
        try:
            # Send download command
            sock.send(f"DOWNLOAD {test_bytes}\n".encode())
            
            # Receive header with total bytes
            header_data = sock.recv(8)
            if len(header_data) < 8:
                raise ConnectionError("Failed to receive header")
            
            total_bytes = struct.unpack(self.HEADER_FORMAT, header_data)[0]
            
            # Receive data and measure time
            bytes_received = 0
            start_time = time.perf_counter()
            
            while bytes_received < total_bytes:
                chunk = sock.recv(self.CHUNK_SIZE)
                if not chunk:
                    break
                bytes_received += len(chunk)
            
            elapsed = time.perf_counter() - start_time
            speed_mbps = (bytes_received * 8) / (elapsed * 1_000_000) if elapsed > 0 else 0
            
            return {
                "bytes": bytes_received,
                "duration_seconds": elapsed,
                "speed_mbps": speed_mbps,
            }
        finally:
            sock.close()
    
    def run_upload_test(self, test_bytes: int = 10 * 1024 * 1024) -> Dict[str, Any]:
        """Run upload speed test (client sends to server)."""
        sock = self._connect()
        try:
            # Send upload command
            sock.send(f"UPLOAD {test_bytes}\n".encode())
            
            # Wait for READY
            response = sock.recv(1024)
            if b"READY" not in response:
                raise ConnectionError("Server not ready for upload")
            
            # Generate and send data
            chunk = bytes([(i * 17 + 31) % 256 for i in range(self.CHUNK_SIZE)])
            bytes_sent = 0
            start_time = time.perf_counter()
            
            while bytes_sent < test_bytes:
                chunk_size = min(self.CHUNK_SIZE, test_bytes - bytes_sent)
                sock.send(chunk[:chunk_size])
                bytes_sent += chunk_size
            
            elapsed = time.perf_counter() - start_time
            
            # Receive result from server
            result = sock.recv(1024).decode()
            
            # Parse server-measured speed
            server_speed = 0.0
            if "speed_mbps=" in result:
                try:
                    server_speed = float(result.split("speed_mbps=")[1].split()[0])
                except Exception:
                    pass
            
            # Use client-side calculation as primary
            speed_mbps = (bytes_sent * 8) / (elapsed * 1_000_000) if elapsed > 0 else 0
            
            return {
                "bytes": bytes_sent,
                "duration_seconds": elapsed,
                "speed_mbps": speed_mbps,
                "server_speed_mbps": server_speed,
            }
        finally:
            sock.close()
    
    def run_full_test(self, duration: int = 5) -> Dict[str, Any]:
        """Run complete speedtest (download + upload + latency)."""
        # Calculate bytes for target duration (assuming ~100 Mbps)
        # Adjust: for a 5 second test at 100 Mbps = 62.5 MB
        test_bytes = duration * 100 * 1024 * 1024 // 8  # Convert to bytes
        
        results = {
            "timestamp": datetime.utcnow().isoformat(),
            "server_host": self.server_host,
            "server_port": self.server_port,
            "download_mbps": None,
            "upload_mbps": None,
            "ping_idle_ms": None,
            "ping_loaded_ms": None,
            "jitter_ms": None,
            "packet_loss_percent": None,
            "test_duration_seconds": 0,
        }
        
        total_start = time.perf_counter()
        
        # First, measure idle ping
        try:
            ping_result = self._measure_ping(self.server_host)
            results["ping_idle_ms"] = ping_result.get("avg_ms")
            results["jitter_ms"] = ping_result.get("jitter_ms")
            results["packet_loss_percent"] = ping_result.get("packet_loss")
        except Exception as e:
            LOGGER.warning(f"Ping measurement failed: {e}")
        
        # Download test
        try:
            download_data = self.run_download_test(test_bytes)
            results["download_mbps"] = download_data.get("speed_mbps")
        except Exception as e:
            LOGGER.error(f"Download test failed: {e}")
        
        # Upload test
        try:
            upload_data = self.run_upload_test(test_bytes)
            results["upload_mbps"] = upload_data.get("speed_mbps")
        except Exception as e:
            LOGGER.error(f"Upload test failed: {e}")
        
        results["test_duration_seconds"] = time.perf_counter() - total_start
        
        return results
    
    def _measure_ping(self, host: str, count: int = 10) -> Dict[str, Any]:
        """Measure ping to host using system ping command."""
        if platform.system() == "Windows":
            cmd = ["ping", "-n", str(count), host]
        else:
            cmd = ["ping", "-c", str(count), host]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        except subprocess.TimeoutExpired:
            return {"avg_ms": None, "jitter_ms": None, "packet_loss": 100}
        
        # Parse ping output
        times = []
        packet_loss = 0
        
        if platform.system() == "Windows":
            time_pattern = r"time[=<](\d+(?:\.\d+)?)\s*ms"
            loss_pattern = r"(\d+)% loss"
        else:
            time_pattern = r"time=(\d+(?:\.\d+)?)\s*ms"
            loss_pattern = r"(\d+(?:\.\d+)?)% packet loss"
        
        for line in result.stdout.split('\n'):
            time_match = re.search(time_pattern, line, re.IGNORECASE)
            if time_match:
                times.append(float(time_match.group(1)))
            
            loss_match = re.search(loss_pattern, line, re.IGNORECASE)
            if loss_match:
                packet_loss = float(loss_match.group(1))
        
        if times:
            avg_ms = sum(times) / len(times)
            if len(times) > 1:
                diffs = [abs(times[i+1] - times[i]) for i in range(len(times)-1)]
                jitter_ms = sum(diffs) / len(diffs)
            else:
                jitter_ms = 0
            
            return {
                "avg_ms": avg_ms,
                "min_ms": min(times),
                "max_ms": max(times),
                "jitter_ms": jitter_ms,
                "packet_loss": packet_loss,
            }
        
        return {"avg_ms": None, "jitter_ms": None, "packet_loss": packet_loss}


def get_local_ip() -> str:
    """Get local IP address of this machine."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def calculate_bufferbloat_grade(idle_ping: float, loaded_ping: float) -> str:
    """
    Calculate bufferbloat grade based on ping increase under load.
    A: < 5ms increase (excellent)
    B: 5-30ms increase (good)
    C: 30-60ms increase (fair)
    D: 60-200ms increase (poor)
    F: > 200ms increase (bad)
    """
    if idle_ping is None or loaded_ping is None:
        return "?"
    
    increase = loaded_ping - idle_ping
    
    if increase < 5:
        return "A"
    elif increase < 30:
        return "B"
    elif increase < 60:
        return "C"
    elif increase < 200:
        return "D"
    else:
        return "F"
