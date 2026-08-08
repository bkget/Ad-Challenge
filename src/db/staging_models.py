"""SQLAlchemy ORM models for the STAGING schema.

Staging tables hold raw, unfiltered, unprocessed data loaded directly
from source files. No aggregation, no filtering, no transformations.
These are 1-to-1 copies of the source data for full auditability.
"""

from sqlalchemy import Column, String, Float, Integer, BigInteger, DateTime, Text, Index
from sqlalchemy.orm import declarative_base

StagingBase = declarative_base()


class RawInventory(StagingBase):
    """Raw ad event log — every impression, click, and engagement row.

    Source: data/campaigns_inventory_updated.csv (350k+ rows, no filtering).
    """
    __tablename__ = "raw_inventory"
    __table_args__ = {"schema": "staging"}

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    campaign_id      = Column(String, index=True)
    game_key         = Column(String, index=True)
    type             = Column(String, index=True)   # impression | first_dropped | click-through-event
    device_type      = Column(String)
    platform_os      = Column(String)
    geo_country      = Column(String)
    timestamp        = Column(DateTime, nullable=True)

    __table_args__ = (
        Index("idx_stg_inv_campaign", "campaign_id"),
        Index("idx_stg_inv_gamekey", "game_key"),
        Index("idx_stg_inv_type", "type"),
        {"schema": "staging"},
    )


class RawBriefing(StagingBase):
    """Raw campaign briefing metadata — one row per campaign, as-is from CSV.

    Source: data/briefing.csv
    """
    __tablename__ = "raw_briefing"
    __table_args__ = {"schema": "staging"}

    id                  = Column(Integer, primary_key=True, autoincrement=True)
    campaign_id         = Column(String, index=True)
    campaign_name       = Column(String)
    campaign_objectives = Column(Text)
    kpis                = Column(Text)
    startdate           = Column(DateTime, nullable=True)
    enddate             = Column(DateTime, nullable=True)
    currency            = Column(String)
    buy_rate_cpe        = Column(Float)
    volume_agreed       = Column(Float)
    gross_cost_budget   = Column(Float)


class RawDesignMetadata(StagingBase):
    """Flattened global_design_data.json — one row per (md5_key, request_id).

    Source: data/global_design_data.json
    The top-level MD5 key and nested request_id are both preserved for full traceability.
    """
    __tablename__ = "raw_design_metadata"
    __table_args__ = {"schema": "staging"}

    id                      = Column(Integer, primary_key=True, autoincrement=True)
    md5_game_key            = Column(String, index=True)   # top-level MD5 key in JSON
    request_id              = Column(String, index=True)   # nested request_id
    n_engagement_labels     = Column(Integer)
    n_click_through_labels  = Column(Integer)
    engagement_labels_text  = Column(Text)
    n_engagement_texts      = Column(Integer)
    engagement_text_content = Column(Text)
    dominant_color_r        = Column(Float)
    dominant_color_g        = Column(Float)
    dominant_color_b        = Column(Float)
    dominant_color_proportion = Column(Float)
    color_saturation_mean   = Column(Float)
    color_luminosity_mean   = Column(Float)
    color_diversity         = Column(Integer)
    brightness              = Column(Float)
    has_video               = Column(Integer)
    video_length_seconds    = Column(Float)
    interaction_direction   = Column(String)
    adunit_width            = Column(Float)
    adunit_height           = Column(Float)
    aspect_ratio            = Column(Float)


class RawCreativeAsset(StagingBase):
    """Registry of physical .png files found on disk.

    Source: filesystem scan of data/Creative Assets_/
    """
    __tablename__ = "raw_creative_assets"
    __table_args__ = {"schema": "staging"}

    id            = Column(Integer, primary_key=True, autoincrement=True)
    filename      = Column(String, unique=True, index=True)
    request_id    = Column(String, index=True)   # 20-char hex suffix from filename
    creative_slug = Column(String)               # everything before the last hyphen+hex
    file_path     = Column(Text)


class RawVisionFeatures(StagingBase):
    """Handcrafted visual features + ResNet50 PCA embeddings per image.

    Source: data/processed/vision_embeddings.parquet
    All 2048-dim embeddings are PCA-reduced to 32 dims before storage.
    """
    __tablename__ = "raw_vision_features"
    __table_args__ = {"schema": "staging"}

    id                   = Column(Integer, primary_key=True, autoincrement=True)
    image_filename       = Column(String, unique=True, index=True)
    request_id           = Column(String, index=True)
    # Handcrafted features
    aspect_ratio         = Column(Float)
    image_width          = Column(Float)
    image_height         = Column(Float)
    brightness_mean      = Column(Float)
    saturation_mean      = Column(Float)
    colorfulness         = Column(Float)
    visual_entropy       = Column(Float)
    color_diversity_score = Column(Float)
    is_dark_background   = Column(Integer)
    is_light_background  = Column(Integer)
    # PCA vision embeddings (32 components)
    vision_pca_0  = Column(Float); vision_pca_1  = Column(Float)
    vision_pca_2  = Column(Float); vision_pca_3  = Column(Float)
    vision_pca_4  = Column(Float); vision_pca_5  = Column(Float)
    vision_pca_6  = Column(Float); vision_pca_7  = Column(Float)
    vision_pca_8  = Column(Float); vision_pca_9  = Column(Float)
    vision_pca_10 = Column(Float); vision_pca_11 = Column(Float)
    vision_pca_12 = Column(Float); vision_pca_13 = Column(Float)
    vision_pca_14 = Column(Float); vision_pca_15 = Column(Float)
    vision_pca_16 = Column(Float); vision_pca_17 = Column(Float)
    vision_pca_18 = Column(Float); vision_pca_19 = Column(Float)
    vision_pca_20 = Column(Float); vision_pca_21 = Column(Float)
    vision_pca_22 = Column(Float); vision_pca_23 = Column(Float)
    vision_pca_24 = Column(Float); vision_pca_25 = Column(Float)
    vision_pca_26 = Column(Float); vision_pca_27 = Column(Float)
    vision_pca_28 = Column(Float); vision_pca_29 = Column(Float)
    vision_pca_30 = Column(Float); vision_pca_31 = Column(Float)
