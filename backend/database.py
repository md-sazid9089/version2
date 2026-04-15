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

# Database URL
DATABASE_URL = f"{settings.db_driver}://{settings.db_user}:{settings.db_password}@{settings.db_host}:{settings.db_port}/{settings.db_name}"

# Create engine
engine = create_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=True,  # Verify connections before using them
    pool_recycle=3600,   # Recycle connections after 1 hour
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
