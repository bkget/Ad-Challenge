"""Database reader for the ML pipeline.

Replaces file-based ingestion (CSV/JSON) by reading directly from the
analytics and staging schemas. This makes the pipeline a proper consumer
of the data warehouse instead of re-reading raw files.

Pattern: analytics schema → ML pipeline → model outputs → analytics schema
"""

import logging
from typing import Tuple

import pandas as pd
from sqlalchemy import text

from src.db.session import engine

logger = logging.getLogger(__name__)


def read_linked_dataset_from_db() -> pd.DataFrame:
    """Read the pre-built linked dataset from the analytics + staging schemas.

    Replaces the full file-based ingestion + entity resolution + KPI table
    pipeline with a single SQL query against the data warehouse.

    Returns
    -------
    pd.DataFrame
        Equivalent to the output of build_linked_dataset() — one row per
        (campaign, creative, device_type, platform_os, geo_country) with
        KPI targets and all design/campaign features joined in.
    """
    logger.info("Reading linked dataset from analytics + staging schemas ...")

    sql = """
        SELECT
            -- KPI targets (from analytics.creative_metrics)
            m.campaign_id,
            m.game_key,
            m.device_type,
            m.platform_os,
            m.geo_country,
            m.n_impressions,
            m.n_engagements,
            m.n_clicks,
            m.engagement_rate,
            m.click_through_rate,

            -- Creative identity (from analytics.creatives)
            c.creative_slug,
            c.creative_request_id,
            c.image_filename,

            -- Campaign context (from analytics.campaigns)
            camp.campaign_name,
            camp.campaign_objectives,
            camp.startdate,
            camp.enddate,
            camp.currency,
            camp.buy_rate_cpe,
            camp.volume_agreed,
            camp.gross_cost_budget,
            -- Computed duration in days
            EXTRACT(DAY FROM (camp.enddate - camp.startdate))::INTEGER
                AS campaign_duration_days,

            -- Creative design features (from staging.raw_design_metadata)
            d.n_engagement_labels,
            d.n_click_through_labels,
            d.engagement_labels_text,
            d.n_engagement_texts,
            d.engagement_text_content,
            d.dominant_color_r,
            d.dominant_color_g,
            d.dominant_color_b,
            d.dominant_color_proportion,
            d.color_saturation_mean,
            d.color_luminosity_mean,
            d.color_diversity,
            d.brightness,
            d.has_video,
            d.video_length_seconds,
            d.interaction_direction,
            d.adunit_width,
            d.adunit_height,
            d.aspect_ratio

        FROM analytics.creative_metrics m

        -- Join creative identity
        LEFT JOIN analytics.creatives c
            ON c.game_key = m.game_key

        -- Join campaign briefing
        LEFT JOIN analytics.campaigns camp
            ON camp.campaign_id = m.campaign_id

        -- Join design metadata via creative_request_id
        LEFT JOIN staging.raw_design_metadata d
            ON d.request_id = c.creative_request_id

        WHERE m.campaign_id IS NOT NULL
        ORDER BY m.campaign_id, m.game_key
    """

    with engine.connect() as conn:
        df = pd.read_sql(text(sql), conn)

    # Parse date columns
    for col in ["startdate", "enddate"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")

    logger.info(
        f"Linked dataset from DB: {len(df):,} rows, "
        f"{df.shape[1]} columns, "
        f"{df['campaign_id'].nunique()} campaigns, "
        f"{df['game_key'].nunique()} unique creatives"
    )
    return df


def read_vision_features_from_db() -> pd.DataFrame:
    """Read pre-extracted vision features from staging.raw_vision_features.

    Replaces the file-based vision parquet cache read. Returns the same
    structure that run_vision_extraction() would produce.

    Returns
    -------
    pd.DataFrame
        One row per image with handcrafted features + PCA vision columns.
    """
    logger.info("Reading vision features from staging.raw_vision_features ...")

    sql = "SELECT * FROM staging.raw_vision_features"

    with engine.connect() as conn:
        df = pd.read_sql(text(sql), conn)

    logger.info(
        f"Vision features from DB: {len(df)} images, {df.shape[1]} columns"
    )
    return df


def read_images_registry_from_db() -> pd.DataFrame:
    """Read the creative asset registry from staging.raw_creative_assets.

    Replaces the filesystem scan (list_creative_images). Used by the
    vision extraction stage to know which images to process.

    Returns
    -------
    pd.DataFrame
        One row per .png file with filename, slug, request_id, filepath.
    """
    logger.info("Reading creative asset registry from staging.raw_creative_assets ...")

    sql = """
        SELECT
            filename,
            file_path   AS filepath,
            creative_slug AS slug,
            request_id
        FROM staging.raw_creative_assets
        ORDER BY filename
    """

    with engine.connect() as conn:
        df = pd.read_sql(text(sql), conn)

    # Add placement_type derived from slug (matches list_creative_images logic)
    def _placement(slug):
        if not isinstance(slug, str):
            return "unknown"
        if "-mob" in slug:
            return "mobile"
        if "-mpu" in slug:
            return "mpu"
        if "-tap" in slug:
            return "tap"
        if "-bio" in slug:
            return "bio"
        return "unknown"

    df["placement_type"] = df["slug"].apply(_placement)

    # Compute file_size_kb dynamically since it's not stored in the staging DB
    import os
    def _get_size(path):
        if pd.isna(path) or not os.path.exists(path):
            return 0.0
        return round(os.path.getsize(path) / 1024, 2)
        
    df["file_size_kb"] = df["filepath"].apply(_get_size)

    logger.info(f"Asset registry from DB: {len(df)} images")
    return df
