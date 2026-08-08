"""SQLAlchemy ORM Models for the Ad-Challenge database."""

from sqlalchemy import Column, String, Float, Integer, Boolean, DateTime, ForeignKey, Index
from sqlalchemy.orm import relationship
from src.db.session import Base
from datetime import datetime

class Campaign(Base):
    __tablename__ = "campaigns"

    campaign_id = Column(String, primary_key=True, index=True)
    campaign_name = Column(String)
    campaign_objectives = Column(String)
    startdate = Column(DateTime, nullable=True)
    enddate = Column(DateTime, nullable=True)
    currency = Column(String)
    buy_rate_cpe = Column(Float)
    volume_agreed = Column(Float)
    gross_cost_budget = Column(Float)
    
    # Relationships
    metrics = relationship("CreativeMetric", back_populates="campaign")


class Creative(Base):
    __tablename__ = "creatives"

    game_key = Column(String, primary_key=True, index=True)
    creative_slug = Column(String, index=True)
    creative_request_id = Column(String, index=True)
    image_filename = Column(String)
    
    # Vision features
    aspect_ratio = Column(Float)
    brightness_mean = Column(Float)
    saturation_mean = Column(Float)
    colorfulness = Column(Float)
    visual_entropy = Column(Float)
    color_diversity_score = Column(Float)
    has_video = Column(Boolean)
    is_dark_background = Column(Boolean)
    is_light_background = Column(Boolean)

    # Relationships
    metrics = relationship("CreativeMetric", back_populates="creative")


class CreativeMetric(Base):
    __tablename__ = "creative_metrics"

    id = Column(Integer, primary_key=True, autoincrement=True)
    campaign_id = Column(String, ForeignKey("campaigns.campaign_id"), index=True)
    game_key = Column(String, ForeignKey("creatives.game_key"), index=True)
    
    # Context
    device_type = Column(String)
    platform_os = Column(String)
    geo_country = Column(String)
    
    # Metrics
    n_impressions = Column(Integer)
    n_engagements = Column(Integer)
    n_clicks = Column(Integer)
    engagement_rate = Column(Float)
    click_through_rate = Column(Float)

    # Relationships
    campaign = relationship("Campaign", back_populates="metrics")
    creative = relationship("Creative", back_populates="metrics")
    
    __table_args__ = (
        Index('idx_campaign_context', 'campaign_id', 'device_type', 'geo_country'),
    )


class ModelBenchmark(Base):
    __tablename__ = "model_benchmarks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_timestamp = Column(DateTime, default=datetime.utcnow)
    target_metric = Column(String)
    model_name = Column(String)
    mae = Column(Float)
    rmse = Column(Float)
    r2 = Column(Float)
    mape = Column(Float)
    n_features = Column(Integer)


class FeatureImportance(Base):
    __tablename__ = "feature_importances"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_timestamp = Column(DateTime, default=datetime.utcnow)
    model_name = Column(String)
    feature_name = Column(String, index=True)
    importance_score = Column(Float)
    category = Column(String) # Contextual vs Visual
