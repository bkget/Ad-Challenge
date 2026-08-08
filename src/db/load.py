"""Two-phase database loader.

Phase 1 — Staging (Raw):
    Bulk-load all raw source data into the `staging` schema with zero filtering.
    Uses pandas.to_sql() for high-speed bulk inserts.

Phase 2 — Analytics (SQL Transforms):
    Build clean, aggregated analytical tables in the `analytics` schema
    using pure SQL queries executed against the staging tables.
    The database engine does the heavy lifting — no Python-side loops.
"""

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session

from src.db.session import engine, SessionLocal
from src.db.staging_models import StagingBase
from src.db.analytics_models import AnalyticsBase

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────
# Schema & Table Initialisation
# ─────────────────────────────────────────────────────────────

def init_schemas(conn):
    """Create schemas and all tables. Drop public schema legacy tables."""
    logger.info("Creating schemas: staging, analytics ...")
    conn.execute(text("CREATE SCHEMA IF NOT EXISTS staging"))
    conn.execute(text("CREATE SCHEMA IF NOT EXISTS analytics")) 

    conn.commit()

    # Create staging tables
    StagingBase.metadata.create_all(bind=engine)
    logger.info("Staging schema tables created.")

    # Create analytics tables
    AnalyticsBase.metadata.create_all(bind=engine)
    logger.info("Analytics schema tables created.")


# ─────────────────────────────────────────────────────────────
# Phase 1 — Staging Loads (Raw, Bulk, No Filtering)
# ─────────────────────────────────────────────────────────────

def load_staging_inventory(conn):
    """Load ALL raw inventory events into staging.raw_inventory."""
    # Skip if already loaded (saves ~2.5min on reruns)
    existing = conn.execute(text("SELECT COUNT(*) FROM staging.raw_inventory")).scalar()
    if existing > 0:
        logger.info(f"Phase 1a: staging.raw_inventory already has {existing:,} rows — skipping reload.")
        return

    logger.info("Phase 1a: Loading raw inventory (all events, no filter) ...")
    path = "data/campaigns_inventory_updated.csv"
    if not Path(path).exists():
        logger.error(f"Not found: {path}")
        return

    # Read only the columns we model; parse timestamp if present
    df = pd.read_csv(path, low_memory=False)

    col_map = {
        "campaign_id": "campaign_id",
        "game_key": "game_key",
        "type": "type",
        "device_type": "device_type",
        "platform_os": "platform_os",
        "geo_country": "geo_country",
    }
    # Keep only columns that exist
    keep = {k: v for k, v in col_map.items() if k in df.columns}
    df = df[list(keep.keys())].rename(columns=keep)

    # Truncate before reload to ensure idempotency
    conn.execute(text("TRUNCATE TABLE staging.raw_inventory RESTART IDENTITY"))
    conn.commit()

    df.to_sql(
        "raw_inventory",
        con=engine,
        schema="staging",
        if_exists="append",
        index=False,
        chunksize=10_000,
        method="multi",
    )
    count = conn.execute(text("SELECT COUNT(*) FROM staging.raw_inventory")).scalar()
    logger.info(f"  → staging.raw_inventory: {count:,} rows loaded.")


def load_staging_briefing(conn):
    """Load raw campaign briefing data into staging.raw_briefing."""
    logger.info("Phase 1b: Loading raw briefing ...")
    path = "data/briefing.csv"
    if not Path(path).exists():
        logger.error(f"Not found: {path}")
        return

    df = pd.read_csv(path, low_memory=False)

    # Normalize column names to match model
    rename = {}
    for col in df.columns:
        norm = col.strip().lower().replace(" ", "_").replace("/", "_").replace("(", "").replace(")", "")
        rename[col] = norm
    df = df.rename(columns=rename)

    # Map to our staging model columns
    col_map = {
        "campaign_id": "campaign_id",
        "campaign_name": "campaign_name",
        "campaign_objectives": "campaign_objectives",
        "kpis": "kpis",
        "startdate": "startdate",
        "enddate": "enddate",
        "currency": "currency",
        "buy_rate_cpe": "buy_rate_cpe",
        "volume_agreed": "volume_agreed",
        "gross_cost_budget": "gross_cost_budget",
    }
    keep = {k: v for k, v in col_map.items() if k in df.columns}
    df = df[list(keep.keys())].rename(columns=keep)

    # Parse dates
    for dcol in ["startdate", "enddate"]:
        if dcol in df.columns:
            df[dcol] = pd.to_datetime(df[dcol], errors="coerce")

    conn.execute(text("TRUNCATE TABLE staging.raw_briefing RESTART IDENTITY"))
    conn.commit()

    df.to_sql("raw_briefing", con=engine, schema="staging", if_exists="append", index=False)
    count = conn.execute(text("SELECT COUNT(*) FROM staging.raw_briefing")).scalar()
    logger.info(f"  → staging.raw_briefing: {count:,} rows loaded.")


def load_staging_design(conn):
    """Flatten global_design_data.json into staging.raw_design_metadata."""
    logger.info("Phase 1c: Loading raw design metadata ...")
    path = "data/global_design_data.json"
    if not Path(path).exists():
        logger.error(f"Not found: {path}")
        return

    with open(path) as f:
        design = json.load(f)

    from src.ingestion.entity_resolution import flatten_global_design
    df = flatten_global_design(design)
    # Rename game_key → md5_game_key to clarify it's the JSON top-level MD5
    df = df.rename(columns={"game_key": "md5_game_key"})

    # Use pandas to auto-create table from actual dataframe schema (avoids column mismatch)
    df.to_sql(
        "raw_design_metadata",
        con=engine,
        schema="staging",
        if_exists="replace",   # drop & recreate with actual columns
        index=False,
        chunksize=5_000,
    )
    count = conn.execute(text("SELECT COUNT(*) FROM staging.raw_design_metadata")).scalar()
    logger.info(f"  → staging.raw_design_metadata: {count:,} rows loaded.")


def load_staging_creative_assets(conn):
    """Scan Creative Assets_ directory and register each .png in staging."""
    logger.info("Phase 1d: Loading raw creative asset registry ...")
    images_dir = Path("data/Creative Assets_")
    if not images_dir.exists():
        logger.error(f"Not found: {images_dir}")
        return

    records = []
    for f in images_dir.glob("*.png"):
        name = f.stem  # filename without .png
        # Last 20 chars before extension = request_id
        parts = name.rsplit("-", 1)
        request_id = parts[1] if len(parts) == 2 else None
        slug = parts[0] if len(parts) == 2 else name
        records.append({
            "filename": f.name,
            "request_id": request_id,
            "creative_slug": slug,
            "file_path": str(f.resolve()),
        })

    df = pd.DataFrame(records)
    conn.execute(text("TRUNCATE TABLE staging.raw_creative_assets RESTART IDENTITY"))
    conn.commit()

    df.to_sql("raw_creative_assets", con=engine, schema="staging", if_exists="append", index=False)
    count = conn.execute(text("SELECT COUNT(*) FROM staging.raw_creative_assets")).scalar()
    logger.info(f"  → staging.raw_creative_assets: {count:,} rows loaded.")


def load_staging_vision(conn):
    """Load vision embeddings parquet into staging.raw_vision_features."""
    logger.info("Phase 1e: Loading raw vision features ...")
    path = "data/processed/vision_embeddings.parquet"
    if not Path(path).exists():
        logger.warning(f"Not found (run ML pipeline first): {path}")
        return

    df = pd.read_parquet(path)

    # Auto-create table from actual parquet schema (handles all 32 PCA columns)
    df.to_sql(
        "raw_vision_features",
        con=engine,
        schema="staging",
        if_exists="replace",
        index=False,
        chunksize=1_000,
    )
    count = conn.execute(text("SELECT COUNT(*) FROM staging.raw_vision_features")).scalar()
    logger.info(f"  → staging.raw_vision_features: {count:,} rows loaded.")


# ─────────────────────────────────────────────────────────────
# Phase 2 — Analytics Transforms (Pure SQL)
# ─────────────────────────────────────────────────────────────

def build_analytics_campaigns(conn):
    """Build analytics.campaigns from staging.raw_briefing."""
    logger.info("Phase 2a: Building analytics.campaigns ...")
    conn.execute(text("TRUNCATE TABLE analytics.campaigns CASCADE"))
    conn.execute(text("""
        INSERT INTO analytics.campaigns (
            campaign_id, campaign_name, campaign_objectives,
            startdate, enddate, currency,
            buy_rate_cpe, volume_agreed, gross_cost_budget
        )
        SELECT DISTINCT ON (campaign_id)
            campaign_id,
            campaign_name,
            campaign_objectives,
            startdate,
            enddate,
            currency,
            COALESCE(buy_rate_cpe, 0.0),
            COALESCE(volume_agreed, 0.0),
            COALESCE(gross_cost_budget, 0.0)
        FROM staging.raw_briefing
        WHERE campaign_id IS NOT NULL
        ORDER BY campaign_id
    """))
    conn.commit()
    count = conn.execute(text("SELECT COUNT(*) FROM analytics.campaigns")).scalar()
    logger.info(f"  → analytics.campaigns: {count:,} rows.")


def build_analytics_creatives(conn):
    """Build analytics.creatives by joining inventory slugs to vision features."""
    logger.info("Phase 2b: Building analytics.creatives ...")
    conn.execute(text("TRUNCATE TABLE analytics.creatives CASCADE"))
    conn.execute(text("""
        INSERT INTO analytics.creatives (
            game_key, creative_slug, creative_request_id, image_filename,
            aspect_ratio, brightness_mean, saturation_mean, colorfulness,
            visual_entropy, color_diversity_score,
            has_video, is_dark_background, is_light_background
        )
        SELECT DISTINCT ON (inv.game_key)
            inv.game_key,
            -- Parse slug: everything before the last '/'
            SPLIT_PART(inv.game_key, '/', 1)                        AS creative_slug,
            -- Parse request_id: everything after the last '/'
            SPLIT_PART(inv.game_key, '/', 2)                        AS creative_request_id,
            -- Reconstruct expected filename
            SPLIT_PART(inv.game_key, '/', 1) || '-' ||
                SPLIT_PART(inv.game_key, '/', 2) || '.png'          AS image_filename,
            -- Vision features from staging (LEFT JOIN — null if no image found)
            COALESCE(v.aspect_ratio, 0.0),
            COALESCE(v.brightness_mean, 0.0),
            COALESCE(v.saturation_mean, 0.0),
            COALESCE(v.colorfulness, 0.0),
            COALESCE(v.visual_entropy, 0.0),
            COALESCE(v.color_diversity_score, 0.0),
            FALSE,                                                   -- has_video (from design, not vision)
            COALESCE((v.is_dark_background::numeric != 0), FALSE),
            COALESCE((v.is_light_background::numeric != 0), FALSE)
        FROM (
            SELECT DISTINCT game_key FROM staging.raw_inventory
            WHERE game_key IS NOT NULL AND game_key LIKE '%/%'
        ) inv
        LEFT JOIN staging.raw_vision_features v
            ON v.filename = (
                SPLIT_PART(inv.game_key, '/', 1) || '-' ||
                SPLIT_PART(inv.game_key, '/', 2) || '.png'
            )
        ORDER BY inv.game_key
    """))
    conn.commit()
    count = conn.execute(text("SELECT COUNT(*) FROM analytics.creatives")).scalar()
    logger.info(f"  → analytics.creatives: {count:,} rows.")


def build_analytics_creative_metrics(conn):
    """Aggregate all raw events into ER/CTR metrics via SQL GROUP BY.

    NO min_impressions filter — all (campaign, creative, context) combinations
    are preserved. Consumers can apply their own WHERE n_impressions >= N.
    """
    logger.info("Phase 2c: Building analytics.creative_metrics (SQL GROUP BY, no filters) ...")
    conn.execute(text("TRUNCATE TABLE analytics.creative_metrics"))
    conn.execute(text("""
        INSERT INTO analytics.creative_metrics (
            campaign_id, game_key,
            device_type, platform_os, geo_country,
            n_impressions, n_engagements, n_clicks,
            engagement_rate, click_through_rate
        )
        SELECT
            campaign_id,
            game_key,
            device_type,
            platform_os,
            geo_country,
            COUNT(*) FILTER (WHERE type = 'impression')              AS n_impressions,
            COUNT(*) FILTER (WHERE type = 'first_dropped')           AS n_engagements,
            COUNT(*) FILTER (WHERE type = 'click-through-event')     AS n_clicks,
            COUNT(*) FILTER (WHERE type = 'first_dropped')::FLOAT
                / NULLIF(COUNT(*) FILTER (WHERE type = 'impression'), 0)
                                                                     AS engagement_rate,
            COUNT(*) FILTER (WHERE type = 'click-through-event')::FLOAT
                / NULLIF(COUNT(*) FILTER (WHERE type = 'impression'), 0)
                                                                     AS click_through_rate
        FROM staging.raw_inventory
        WHERE
            campaign_id IS NOT NULL
            AND game_key IS NOT NULL
            AND game_key LIKE '%/%'
            -- Only keep rows whose game_key maps to a known creative
            AND game_key IN (SELECT game_key FROM analytics.creatives)
        GROUP BY
            campaign_id, game_key, device_type, platform_os, geo_country
    """))
    conn.commit()
    count = conn.execute(text("SELECT COUNT(*) FROM analytics.creative_metrics")).scalar()
    logger.info(f"  → analytics.creative_metrics: {count:,} rows.")


def build_analytics_benchmarks(conn):
    """Load ML benchmark results and feature importances from JSON into analytics."""
    logger.info("Phase 2d: Building analytics.model_benchmarks & feature_importances ...")
    path = "results/benchmark_results.json"
    if not Path(path).exists():
        logger.warning(f"Not found (run ML pipeline first): {path}")
        return

    with open(path) as f:
        bench = json.load(f)

    conn.execute(text("TRUNCATE TABLE analytics.model_benchmarks"))
    conn.execute(text("TRUNCATE TABLE analytics.feature_importances"))
    conn.commit()

    target = bench.get("target", "engagement_rate")
    models = bench.get("models", {})
    ts = datetime.now(timezone.utc)

    for model_name, metrics in models.items():
        if "error" in metrics:
            continue
        conn.execute(text("""
            INSERT INTO analytics.model_benchmarks
                (run_timestamp, target_metric, model_name, mae, rmse, r2, mape, n_features)
            VALUES
                (:ts, :target, :model, :mae, :rmse, :r2, :mape, :n_feat)
        """), {
            "ts": ts, "target": target, "model": model_name,
            "mae": metrics.get("mae_mean", 0.0),
            "rmse": metrics.get("rmse_mean", 0.0),
            "r2": metrics.get("r2_mean", 0.0),
            "mape": metrics.get("mape_mean", 0.0),
            "n_feat": metrics.get("n_features", 0),
        })

        visual_prefixes = ("vision_", "color_", "dominant_", "brightness", "saturation",
                           "aspect_", "visual_", "is_")
        for feat, score in metrics.get("feature_importance", {}).items():
            category = "Visual" if str(feat).startswith(visual_prefixes) else "Contextual"
            conn.execute(text("""
                INSERT INTO analytics.feature_importances
                    (run_timestamp, model_name, feature_name, importance_score, category)
                VALUES (:ts, :model, :feat, :score, :cat)
            """), {"ts": ts, "model": model_name, "feat": feat, "score": score, "cat": category})

    conn.commit()
    bm_count = conn.execute(text("SELECT COUNT(*) FROM analytics.model_benchmarks")).scalar()
    fi_count = conn.execute(text("SELECT COUNT(*) FROM analytics.feature_importances")).scalar()
    logger.info(f"  → analytics.model_benchmarks: {bm_count} rows.")
    logger.info(f"  → analytics.feature_importances: {fi_count} rows.")


# ─────────────────────────────────────────────────────────────
# Entrypoint
# ─────────────────────────────────────────────────────────────

def run():
    with engine.connect() as conn:
        # ── Bootstrap ──
        init_schemas(conn)

        # ── Phase 1: Stage Raw Data ──
        logger.info("=" * 60)
        logger.info("PHASE 1 — Staging raw source data ...")
        logger.info("=" * 60)
        load_staging_inventory(conn)
        load_staging_briefing(conn)
        load_staging_design(conn)
        load_staging_creative_assets(conn)
        load_staging_vision(conn)

        # ── Phase 2: Build Analytics via SQL ──
        logger.info("=" * 60)
        logger.info("PHASE 2 — Building analytics schema via SQL transforms ...")
        logger.info("=" * 60)
        build_analytics_campaigns(conn)
        build_analytics_creatives(conn)
        build_analytics_creative_metrics(conn)
        build_analytics_benchmarks(conn)

    logger.info("=" * 60)
    logger.info("Database load complete. Staging + Analytics schemas ready.")
    logger.info("=" * 60)


if __name__ == "__main__":
    run()
