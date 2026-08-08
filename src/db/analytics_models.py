"""SQLAlchemy ORM models for the ANALYTICS schema.

Analytics tables are the clean, ML-ready, deduplicated tables used by
the FastAPI backend and all downstream consumers. They are built from
the staging schema via SQL transforms — never loaded directly from files.
"""

from datetime import datetime
from sqlalchemy import Column, String, Float, Integer, Boolean, DateTime, Text, Index, ForeignKey
from sqlalchemy.orm import declarative_base, relationship

AnalyticsBase = declarative_base()


class Campaign(AnalyticsBase):
    """One row per unique campaign, deduplicated from staging.raw_briefing."""
    __tablename__ = "campaigns"
    __table_args__ = {"schema": "analytics"}

    campaign_id         = Column(String, primary_key=True, index=True)
    campaign_name       = Column(String)
    campaign_objectives = Column(Text)
    startdate           = Column(DateTime, nullable=True)
    enddate             = Column(DateTime, nullable=True)
    currency            = Column(String)
    buy_rate_cpe        = Column(Float)
    volume_agreed       = Column(Float)
    gross_cost_budget   = Column(Float)

    metrics = relationship("CreativeMetric", back_populates="campaign")


class Creative(AnalyticsBase):
    """One row per unique creative (game_key), enriched with vision features."""
    __tablename__ = "creatives"
    __table_args__ = {"schema": "analytics"}

    game_key             = Column(String, primary_key=True, index=True)
    creative_slug        = Column(String, index=True)
    creative_request_id  = Column(String, index=True)
    image_filename       = Column(String)

    # Handcrafted vision features
    aspect_ratio         = Column(Float)
    brightness_mean      = Column(Float)
    saturation_mean      = Column(Float)
    colorfulness         = Column(Float)
    visual_entropy       = Column(Float)
    color_diversity_score = Column(Float)
    has_video            = Column(Boolean)
    is_dark_background   = Column(Boolean)
    is_light_background  = Column(Boolean)

    metrics = relationship("CreativeMetric", back_populates="creative")


class CreativeMetric(AnalyticsBase):
    """Aggregated ER/CTR per (campaign, creative, device, os, country).

    Built via SQL GROUP BY from staging.raw_inventory — NO min_impressions filter.
    All combinations are preserved; filtering can be applied at query time.
    """
    __tablename__ = "creative_metrics"
    __table_args__ = (
        Index("idx_anl_metric_campaign", "campaign_id"),
        Index("idx_anl_metric_gamekey", "game_key"),
        Index("idx_anl_metric_context", "campaign_id", "device_type", "geo_country"),
        {"schema": "analytics"},
    )

    id                 = Column(Integer, primary_key=True, autoincrement=True)
    campaign_id        = Column(String, ForeignKey("analytics.campaigns.campaign_id"), index=True)
    game_key           = Column(String, ForeignKey("analytics.creatives.game_key"), index=True)
    device_type        = Column(String)
    platform_os        = Column(String)
    geo_country        = Column(String)
    n_impressions      = Column(Integer)
    n_engagements      = Column(Integer)
    n_clicks           = Column(Integer)
    engagement_rate    = Column(Float)
    click_through_rate = Column(Float)

    campaign = relationship("Campaign", back_populates="metrics")
    creative = relationship("Creative", back_populates="metrics")


class ModelBenchmark(AnalyticsBase):
    """ML model evaluation results per run."""
    __tablename__ = "model_benchmarks"
    __table_args__ = {"schema": "analytics"}

    id             = Column(Integer, primary_key=True, autoincrement=True)
    run_timestamp  = Column(DateTime, default=datetime.utcnow)
    target_metric  = Column(String)
    model_name     = Column(String)
    mae            = Column(Float)
    rmse           = Column(Float)
    r2             = Column(Float)
    mape           = Column(Float)
    n_features     = Column(Integer)


class FeatureImportance(AnalyticsBase):
    """Feature importance scores per model per run."""
    __tablename__ = "feature_importances"
    __table_args__ = {"schema": "analytics"}

    id               = Column(Integer, primary_key=True, autoincrement=True)
    run_timestamp    = Column(DateTime, default=datetime.utcnow)
    model_name       = Column(String)
    feature_name     = Column(String, index=True)
    importance_score = Column(Float)
    category         = Column(String)   # "Visual" | "Contextual"
