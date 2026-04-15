"""
Database Configuration and Connection
======================================
Supports Azure SQL (MSSQL) via pyodbc. Zero changes to business logic.

Connection priority:
  1. DATABASE_URL env var  →  full connection string (recommended)
  2. Individual DB_* env vars  →  auto-composed into connection string

Usage:
  from database import SessionLocal

  db = SessionLocal()
  # ... use db for queries
  db.close()

Or with FastAPI dependency injection:
  from database import get_db
  from fastapi import Depends
  def my_route(db = Depends(get_db)): ...
"""

import urllib.parse
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from config import settings

# ─── Resolve DATABASE_URL ─────────────────────────────────────────────────────
# Priority 1: Full DATABASE_URL env var (recommended for Azure deployments)
# Priority 2: Compose from individual DB_* env vars using ODBC Driver 18
if settings.database_url:
    _url = settings.database_url.strip()
    # Guard against common copy-paste mistake: pasting "DATABASE_URL=mssql+..."
    # as the value instead of just "mssql+..."
    if "=" in _url and _url.split("=", 1)[0].strip().upper() == "DATABASE_URL":
        _url = _url.split("=", 1)[1].strip()
    DATABASE_URL = _url
else:
    # Build Azure SQL ODBC connection string from individual settings
    odbc_str = (
        f"DRIVER={{ODBC Driver 18 for SQL Server}};"
        f"SERVER={settings.db_host},{settings.db_port};"
        f"DATABASE={settings.db_name};"
        f"UID={settings.db_user};"
        f"PWD={settings.db_password};"
        f"Encrypt=yes;"
        f"TrustServerCertificate=no;"
        f"Connection Timeout=30;"
    )
    DATABASE_URL = f"mssql+pyodbc:///?odbc_connect={urllib.parse.quote_plus(odbc_str)}"

# ─── Driver-specific connect_args ─────────────────────────────────────────────
# fast_executemany=True significantly speeds up bulk inserts on MSSQL/pyodbc
connect_args = {"fast_executemany": True}

# ─── Engine ───────────────────────────────────────────────────────────────────
engine = create_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=True,   # Automatically drop stale connections
    pool_recycle=1800,    # Recycle every 30 min — Azure SQL closes idle connections
    pool_size=5,
    max_overflow=10,
    connect_args=connect_args,
)

# ─── Session Factory ──────────────────────────────────────────────────────────
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for ORM models
Base = declarative_base()


def get_db():
    """Dependency injection for database sessions (use with FastAPI Depends)."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
