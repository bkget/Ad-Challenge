"""Script to load ML pipeline data into PostgreSQL for the API."""

import json
import logging
from datetime import datetime, timezone
import pandas as pd
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from src.db.session import engine, SessionLocal, Base
from src.db.models import Campaign, Creative, CreativeMetric, ModelBenchmark, FeatureImportance

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)


def init_db():
    """Create all tables."""
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables created.")


def load_data(db: Session):
    """Load data from parquet and json files into the database."""
    
    # 1. Load Parquet Data
    try:
        df = pd.read_parquet("data/processed/feature_dataset.parquet")
    except FileNotFoundError:
        logger.error("Feature dataset not found. Run ML pipeline first.")
        return

    # Fill NaNs for DB insertion
    df = df.where(pd.notnull(df), None)

    # 1.1 Load Campaigns
    logger.info("Loading Campaigns...")
    campaign_cols = [
        "campaign_id", "campaign_name", "campaign_objectives", 
        "startdate", "enddate", "currency", "buy_rate_cpe", 
        "volume_agreed", "gross_cost_budget"
    ]
    # Ensure cols exist
    available_camp_cols = [c for c in campaign_cols if c in df.columns]
    camp_df = df[available_camp_cols].drop_duplicates(subset=["campaign_id"])
    
    for _, row in camp_df.iterrows():
        camp = db.query(Campaign).filter(Campaign.campaign_id == row["campaign_id"]).first()
        if not camp:
            # Handle timestamps carefully
            start = row.get("startdate")
            end = row.get("enddate")
            if pd.isna(start) or start is None: start = None
            if pd.isna(end) or end is None: end = None
            
            camp = Campaign(
                campaign_id=row["campaign_id"],
                campaign_name=row.get("campaign_name", "Unknown"),
                campaign_objectives=row.get("campaign_objectives", ""),
                startdate=start,
                enddate=end,
                currency=row.get("currency", "USD"),
                buy_rate_cpe=float(row.get("buy_rate_cpe") or 0.0),
                volume_agreed=float(row.get("volume_agreed") or 0.0),
                gross_cost_budget=float(row.get("gross_cost_budget") or 0.0)
            )
            db.add(camp)
    
    try:
        db.commit()
    except IntegrityError as e:
        db.rollback()
        logger.warning(f"Campaign integrity error: {e}")

    # 1.2 Load Creatives
    logger.info("Loading Creatives...")
    # creative identifiers
    # the feature dataset has game_key_x and game_key_y due to some joins. we use game_key_x as primary
    game_key_col = "game_key_x" if "game_key_x" in df.columns else "game_key"
    
    creative_cols = [
        game_key_col, "creative_slug", "creative_request_id", "image_filename",
        "aspect_ratio", "brightness_mean", "saturation_mean", "colorfulness",
        "visual_entropy", "color_diversity_score", "has_video", 
        "is_dark_background", "is_light_background"
    ]
    available_crea_cols = [c for c in creative_cols if c in df.columns]
    crea_df = df[available_crea_cols].drop_duplicates(subset=[game_key_col])
    
    for _, row in crea_df.iterrows():
        gk = row[game_key_col]
        crea = db.query(Creative).filter(Creative.game_key == gk).first()
        if not crea:
            crea = Creative(
                game_key=gk,
                creative_slug=row.get("creative_slug"),
                creative_request_id=row.get("creative_request_id"),
                image_filename=row.get("image_filename"),
                aspect_ratio=float(row.get("aspect_ratio") or 0.0),
                brightness_mean=float(row.get("brightness_mean") or 0.0),
                saturation_mean=float(row.get("saturation_mean") or 0.0),
                colorfulness=float(row.get("colorfulness") or 0.0),
                visual_entropy=float(row.get("visual_entropy") or 0.0),
                color_diversity_score=float(row.get("color_diversity_score") or 0.0),
                has_video=bool(row.get("has_video") or 0),
                is_dark_background=bool(row.get("is_dark_background") or 0),
                is_light_background=bool(row.get("is_light_background") or 0)
            )
            db.add(crea)

    try:
        db.commit()
    except IntegrityError as e:
        db.rollback()
        logger.warning(f"Creative integrity error: {e}")

    # 1.3 Load Creative Metrics
    logger.info("Loading Creative Metrics...")
    # Delete existing metrics to avoid uncontrolled duplicates
    db.query(CreativeMetric).delete()
    
    for _, row in df.iterrows():
        metric = CreativeMetric(
            campaign_id=row.get("campaign_id"),
            game_key=row.get(game_key_col),
            device_type=row.get("device_type"),
            platform_os=row.get("platform_os"),
            geo_country=row.get("geo_country"),
            n_impressions=int(row.get("n_impressions") or 0),
            n_engagements=int(row.get("n_engagements") or 0),
            n_clicks=int(row.get("n_clicks") or 0),
            engagement_rate=float(row.get("engagement_rate") or 0.0),
            click_through_rate=float(row.get("click_through_rate") or 0.0)
        )
        db.add(metric)
        
    db.commit()

    # 2. Load Benchmark Results
    logger.info("Loading Benchmark Results & Feature Importances...")
    try:
        with open("results/benchmark_results.json", "r") as f:
            bench_results = json.load(f)
            
        target = bench_results.get("target", "engagement_rate")
        models = bench_results.get("models", {})
        
        db.query(ModelBenchmark).delete()
        db.query(FeatureImportance).delete()
        
        ts = datetime.now(timezone.utc)
        
        for model_name, metrics in models.items():
            if "error" in metrics:
                continue
                
            bm = ModelBenchmark(
                run_timestamp=ts,
                target_metric=target,
                model_name=model_name,
                mae=metrics.get("mae_mean", 0.0),
                rmse=metrics.get("rmse_mean", 0.0),
                r2=metrics.get("r2_mean", 0.0),
                mape=metrics.get("mape_mean", 0.0),
                n_features=metrics.get("n_features", 0)
            )
            db.add(bm)
            
            # Load Feature Importances (only available for tree models usually)
            if "feature_importance" in metrics:
                fi = metrics["feature_importance"]
                visual_prefixes = ("vision_", "color_", "dominant_", "brightness", "saturation", "aspect_", "visual_", "is_")
                
                for feat, score in fi.items():
                    category = "Visual" if str(feat).startswith(visual_prefixes) else "Contextual"
                    f_imp = FeatureImportance(
                        run_timestamp=ts,
                        model_name=model_name,
                        feature_name=feat,
                        importance_score=score,
                        category=category
                    )
                    db.add(f_imp)
                    
        db.commit()
    except FileNotFoundError:
        logger.warning("benchmark_results.json not found.")

    logger.info("Data loading complete!")


if __name__ == "__main__":
    init_db()
    db = SessionLocal()
    try:
        load_data(db)
    finally:
        db.close()
