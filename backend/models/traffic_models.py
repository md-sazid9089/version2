"""
Traffic Models
==============
SQLAlchemy model that stores dummy per-road, per-hour traffic levels.
"""

from sqlalchemy import Column, Integer, String, Float, DateTime, UniqueConstraint, Index, func

from database import Base


class RoadTrafficObservation(Base):
    """Per-edge hourly traffic condition (dummy dataset used for ML training)."""

    __tablename__ = "road_traffic_observations"
    __table_args__ = (
        UniqueConstraint("edge_id", "hour_of_day", name="uq_traffic_edge_hour"),
        Index("ix_traffic_edge_hour", "edge_id", "hour_of_day"),
    )

    id = Column(Integer, primary_key=True, index=True)
    edge_id = Column(String(128), nullable=False, index=True)
    road_type = Column(String(64), nullable=False, default="unknown")
    length_m = Column(Float, nullable=False, default=0.0)
    hour_of_day = Column(Integer, nullable=False)
    jam_level = Column(Integer, nullable=False)  # Low=1, Moderate=2, Heavy=3
    jam_label = Column(String(16), nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
