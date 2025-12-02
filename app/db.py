"""Database utilities and ORM models."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterator, Optional

from sqlalchemy import BigInteger, DateTime, Float, Integer, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker


class Base(DeclarativeBase):
    pass


class Measurement(Base):
    __tablename__ = "measurements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    measurement_type: Mapped[str] = mapped_column(String(32), index=True)
    server: Mapped[Optional[str]] = mapped_column(String(128))
    ping_idle_ms: Mapped[Optional[float]] = mapped_column(Float)
    jitter_ms: Mapped[Optional[float]] = mapped_column(Float)
    download_mbps: Mapped[Optional[float]] = mapped_column(Float)
    upload_mbps: Mapped[Optional[float]] = mapped_column(Float)
    ping_during_download_ms: Mapped[Optional[float]] = mapped_column(Float)
    ping_during_upload_ms: Mapped[Optional[float]] = mapped_column(Float)
    download_latency_ms: Mapped[Optional[float]] = mapped_column(Float)
    upload_latency_ms: Mapped[Optional[float]] = mapped_column(Float)
    bytes_used: Mapped[Optional[int]] = mapped_column(BigInteger)
    raw_json: Mapped[str] = mapped_column(Text)


def init_db(data_dir: Path) -> sessionmaker:
    db_path = data_dir / "metrics.db"
    engine = create_engine(f"sqlite:///{db_path}", future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, future=True, expire_on_commit=False)


@contextmanager
def get_session(Session: sessionmaker) -> Iterator:
    session = Session()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
