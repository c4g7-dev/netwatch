"""Database models and utilities for internal network testing."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterator, Optional

from sqlalchemy import BigInteger, Boolean, DateTime, Float, Integer, String, Text, create_engine, ForeignKey
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker, relationship


class InternalBase(DeclarativeBase):
    pass


class Device(InternalBase):
    """Represents a device on the local network."""
    __tablename__ = "devices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    mac_address: Mapped[str] = mapped_column(String(17), unique=True, index=True)
    ip_address: Mapped[str] = mapped_column(String(45))
    hostname: Mapped[Optional[str]] = mapped_column(String(255))
    friendly_name: Mapped[Optional[str]] = mapped_column(String(255))
    connection_type: Mapped[str] = mapped_column(String(10), default="unknown")  # 'lan', 'wifi', 'vpn', 'unknown'
    is_local: Mapped[bool] = mapped_column(Boolean, default=False)  # Is this the machine running the server
    first_seen: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_seen: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    
    # Relationships
    measurements: Mapped[list["InternalMeasurement"]] = relationship("InternalMeasurement", back_populates="device")


class InternalMeasurement(InternalBase):
    """Internal network speed test measurement."""
    __tablename__ = "internal_measurements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    device_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("devices.id"), index=True, nullable=True)
    
    # Connection info
    connection_type: Mapped[str] = mapped_column(String(10))  # 'lan', 'wifi', 'vpn', 'unknown'
    
    # Speed metrics
    download_mbps: Mapped[Optional[float]] = mapped_column(Float)
    upload_mbps: Mapped[Optional[float]] = mapped_column(Float)
    
    # Latency metrics
    ping_idle_ms: Mapped[Optional[float]] = mapped_column(Float)
    ping_loaded_ms: Mapped[Optional[float]] = mapped_column(Float)
    jitter_ms: Mapped[Optional[float]] = mapped_column(Float)
    packet_loss_percent: Mapped[Optional[float]] = mapped_column(Float)
    
    # Bufferbloat (latency under load)
    ping_during_download_ms: Mapped[Optional[float]] = mapped_column(Float)
    ping_during_upload_ms: Mapped[Optional[float]] = mapped_column(Float)
    bufferbloat_grade: Mapped[Optional[str]] = mapped_column(String(2))  # A, B, C, D, F
    
    # Gateway ping (local router latency)
    gateway_ping_ms: Mapped[Optional[float]] = mapped_column(Float)
    
    # Local network latency (to gateway/localhost)
    local_latency_ms: Mapped[Optional[float]] = mapped_column(Float)
    
    # Additional info
    test_duration_seconds: Mapped[Optional[float]] = mapped_column(Float)
    bytes_transferred: Mapped[Optional[int]] = mapped_column(BigInteger)
    raw_json: Mapped[Optional[str]] = mapped_column(Text)
    
    # Relationship (optional - measurement may not be linked to a device)
    device: Mapped[Optional["Device"]] = relationship("Device", back_populates="measurements")


class ServerStatus(InternalBase):
    """Tracks internal speedtest server status."""
    __tablename__ = "server_status"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    is_running: Mapped[bool] = mapped_column(Boolean, default=False)
    port: Mapped[int] = mapped_column(Integer, default=5201)
    clients_connected: Mapped[int] = mapped_column(Integer, default=0)
    total_tests_run: Mapped[int] = mapped_column(Integer, default=0)


def init_internal_db(data_dir: Path) -> sessionmaker:
    """Initialize the internal network database."""
    db_path = data_dir / "internal_metrics.db"
    engine = create_engine(f"sqlite:///{db_path}", future=True)
    InternalBase.metadata.create_all(engine)
    return sessionmaker(bind=engine, future=True, expire_on_commit=False)


@contextmanager
def get_internal_session(Session: sessionmaker) -> Iterator:
    """Context manager for database sessions."""
    session = Session()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
