"""
Database Configuration and Connection
======================================
Provides SQLAlchemy Engine and Session factory for database operations.

Usage:
  from database import SessionLocal
  
  db = SessionLocal()
  # ... use db for queries
  db.close()

Or with context manager:
  with SessionLocal() as db:
    # ... use db for queries
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from config import settings

# Database URL — defaults to local SQLite file; override via DATABASE_URL env var
DATABASE_URL = settings.database_url or "sqlite:///./golitransit.db"

IS_SQLITE = DATABASE_URL.startswith("sqlite")

# SQLite needs check_same_thread=False for FastAPI; MySQL/Postgres need no extra args here
connect_args = {"check_same_thread": False} if IS_SQLITE else {}

# SSL for remote MySQL/PostgreSQL (skipped for SQLite)
if not IS_SQLITE and "ssl_disabled=true" not in DATABASE_URL and settings.db_ssl_mode.lower() == "require":
    connect_args = {"ssl": {"ca": "/etc/ssl/certs/ca-certificates.crt"}}

# Create engine
engine = create_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
    # pool_recycle not supported by SQLite's StaticPool
    **({} if IS_SQLITE else {"pool_recycle": 3600}),
    connect_args=connect_args,
)

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for ORM models
Base = declarative_base()


def get_db():
    """Dependency injection for database sessions."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
