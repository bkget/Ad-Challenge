"""Pipeline orchestrator: the main entry point for the Ad-Challenge ML pipeline.

Replaces the heavy Apache Airflow setup with a lightweight, modular Python runner.

Key design principles:
  - Each stage checks for cached outputs before running (idempotency)
  - Business logic lives in src/* modules (can be imported by Airflow/Prefect in production)
  - Single YAML config drives all parameters
  - Can run the full pipeline or individual stages

Usage:
    # Full pipeline:
    python -m src.pipeline.run_all

    # With custom config:
    python -m src.pipeline.run_all --config configs/default.yaml

    # Specific stage only:
    python -m src.pipeline.run_all --stage vision
    python -m src.pipeline.run_all --stage training
    python -m src.pipeline.run_all --stage benchmark

    # Force recompute (ignore cache):
    python -m src.pipeline.run_all --force
"""

import argparse
import json
import logging
import sys
import time
from pathlib import Path

import yaml

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("pipeline")


def load_config(config_path: str = "configs/default.yaml") -> dict:
    """Load and return the pipeline configuration."""
    with open(config_path, "r") as f:
        config = yaml.safe_load(f)
    logger.info(f"Configuration loaded from {config_path}")
    return config


def stage_ingestion(config: dict) -> tuple:
    """Stage 1: Load all raw data sources."""
    logger.info("\n" + "-" * 50)
    logger.info("STAGE 1: DATA INGESTION & ENTITY RESOLUTION")
    logger.info("-" * 50)

    from src.ingestion.loader import run_ingestion
    from src.ingestion.entity_resolution import (
        flatten_global_design,
        build_creative_kpi_table,
        build_linked_dataset,
    )

    t0 = time.time()
    briefing_df, inventory_df, design_dict, image_features, images_df = run_ingestion(config)
    logger.info(f"  Raw data loaded in {time.time()-t0:.1f}s")

    t0 = time.time()
    design_flat_df = flatten_global_design(design_dict)
    logger.info(f"  Design data flattened in {time.time()-t0:.1f}s")

    t0 = time.time()
    kpi_df = build_creative_kpi_table(
        inventory_df,
        min_impressions=config["features"]["min_impressions"],
    )
    logger.info(f"  KPI table built in {time.time()-t0:.1f}s")

    linked_df = build_linked_dataset(kpi_df, design_flat_df, briefing_df)

    return linked_df, images_df


def stage_vision(images_df, config: dict, force: bool = False):
    """Stage 2: Extract vision features from creative images."""
    logger.info("\n" + "-" * 50)
    logger.info("STAGE 2: VISION FEATURE EXTRACTION")
    logger.info("-" * 50)

    from src.vision.extractor import run_vision_extraction

    t0 = time.time()
    vision_df = run_vision_extraction(images_df, config, force_recompute=force)
    logger.info(f"  Vision extraction completed in {time.time()-t0:.1f}s")
    logger.info(f"  Vision features: {len(vision_df)} images, {vision_df.shape[1]} features")

    return vision_df


def stage_features(linked_df, vision_df, config: dict, force: bool = False):
    """Stage 3: Build the merged feature dataset."""
    logger.info("\n" + "-" * 50)
    logger.info("STAGE 3: FEATURE ENGINEERING")
    logger.info("-" * 50)

    from src.features.build_dataset import run_feature_engineering

    t0 = time.time()
    feature_df = run_feature_engineering(
        linked_df=linked_df,
        vision_df=vision_df,
        config=config,
        force_recompute=force,
    )
    logger.info(f"  Feature engineering completed in {time.time()-t0:.1f}s")
    logger.info(f"  Feature dataset: {len(feature_df):,} rows x {feature_df.shape[1]} cols")

    return feature_df


def stage_benchmark(feature_df, config: dict, force: bool = False):
    """Stage 4: Run GroupKFold benchmark across all 4 model types."""
    logger.info("\n" + "-" * 50)
    logger.info("STAGE 4: BENCHMARK EVALUATION (GroupKFold)")
    logger.info("-" * 50)

    from src.evaluation.benchmark import run_benchmark

    t0 = time.time()
    results = run_benchmark(feature_df, config, force_recompute=force)
    logger.info(f"  Benchmark completed in {time.time()-t0:.1f}s")

    return results


def stage_train_final(feature_df, config: dict):
    """Stage 5: Train final multimodal model on all data for inference."""
    logger.info("\n" + "-" * 50)
    logger.info("STAGE 5: FINAL MODEL TRAINING (for inference)")
    logger.info("-" * 50)

    import pickle
    from pathlib import Path

    from src.features.build_dataset import get_feature_sets, build_feature_matrix
    from src.models.train import train_lightgbm, save_model

    models_dir = config["pipeline"]["models_dir"]
    target_er = config["features"]["target_er"]

    feature_sets = get_feature_sets(feature_df)

    # Train final multimodal model on ALL data (for deployment/demo)
    mask = feature_df[target_er].notna()
    X_all = feature_df[mask][feature_sets["multimodal"]].fillna(0)
    y_er = feature_df[mask][target_er]

    logger.info(f"  Training final multimodal model on {len(X_all):,} samples...")
    model_er = train_lightgbm(X_all, y_er, config)
    save_model(model_er, models_dir, "multimodal")

    # Also train CTR model
    target_ctr = config["features"]["target_ctr"]
    if target_ctr in feature_df.columns:
        y_ctr = feature_df[mask][target_ctr]
        model_ctr = train_lightgbm(X_all, y_ctr, config)
        save_model(model_ctr, models_dir, "multimodal_ctr")

    logger.info(f"  Final models saved to {models_dir}/")


def print_summary(results: dict) -> None:
    """Print a clean benchmark results summary to console."""
    print("\n" + "=" * 65)
    print(" AD CHALLENGE - CREATIVE PERFORMANCE PREDICTION BENCHMARK")
    print("=" * 65)
    print(f" Target: {results.get('target', 'N/A')}")
    print(f" Dataset: {results.get('dataset_size', 0):,} samples | {results.get('n_campaigns', 0)} campaigns")
    print(f" Strategy: GroupKFold (by campaign_id) -- cold-start evaluation")
    print("-" * 65)
    print(f" {'Model':<18} {'MAE':>8} {'RMSE':>8} {'R2':>8} {'MAPE%':>8} {'Features':>10}")
    print("-" * 65)

    for model_name, m in results.get("models", {}).items():
        if "error" in m:
            print(f" {model_name:<18} {'SKIPPED':>8}")
            continue
        mae = m.get("mae_mean", float("nan"))
        rmse = m.get("rmse_mean", float("nan"))
        r2 = m.get("r2_mean", float("nan"))
        mape = m.get("mape_mean", float("nan"))
        n_feats = m.get("n_features", 0)
        print(f" {model_name:<18} {mae:>8.4f} {rmse:>8.4f} {r2:>8.4f} {mape:>8.2f} {n_feats:>10}")

    print("=" * 65)
    print()



def main():
    parser = argparse.ArgumentParser(
        description="Ad-Challenge Multimodal ML Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--config",
        type=str,
        default="configs/default.yaml",
        help="Path to pipeline configuration YAML",
    )
    parser.add_argument(
        "--stage",
        type=str,
        choices=["ingestion", "vision", "features", "benchmark", "training", "all"],
        default="all",
        help="Which pipeline stage to run",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force recompute all stages (ignore cache)",
    )
    args = parser.parse_args()

    logger.info("\n" + "=" * 50)
    logger.info("  AD-CHALLENGE ML PIPELINE")
    logger.info("=" * 50)

    config = load_config(args.config)
    stage = args.stage
    force = args.force

    t_total = time.time()

    if stage in ("ingestion", "all"):
        linked_df, images_df = stage_ingestion(config)
    else:
        import pandas as pd
        cache = Path(config["features"]["feature_cache_path"])
        if cache.exists():
            feature_df = pd.read_parquet(cache)
            linked_df, images_df = None, None
        else:
            logger.error(
                "Feature cache not found. Run full pipeline first:\n"
                "  python -m src.pipeline.run_all"
            )
            sys.exit(1)

    if stage in ("vision", "all") and images_df is not None:
        vision_df = stage_vision(images_df, config, force=force)
    else:
        import pandas as pd
        vision_cache = Path(config["vision"]["cache_path"])
        vision_df = pd.read_parquet(vision_cache) if vision_cache.exists() else None

    if stage in ("features", "all") and linked_df is not None:
        feature_df = stage_features(linked_df, vision_df, config, force=force)
    elif stage not in ("benchmark", "training") and "feature_df" not in dir():
        import pandas as pd
        feature_df = pd.read_parquet(config["features"]["feature_cache_path"])

    if stage in ("benchmark", "all"):
        results = stage_benchmark(feature_df, config, force=force)
        print_summary(results)

    if stage in ("training", "all"):
        stage_train_final(feature_df, config)

    elapsed = time.time() - t_total
    logger.info(f"\n Pipeline completed in {elapsed:.1f}s")


if __name__ == "__main__":
    main()
