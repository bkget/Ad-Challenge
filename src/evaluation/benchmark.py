"""Benchmark evaluation using GroupKFold cross-validation.

The 4-way benchmark design answers the key interview question:
    "Does image data actually improve creative performance prediction?"

By comparing:
  A) Baseline   - Global mean (no features)
  B) Tabular    - Campaign context + creative metadata only
  C) Vision     - Visual embeddings + handcrafted features only
  D) Multimodal - Tabular + Vision (all features)

GroupKFold strategy (grouped by campaign_id) ensures:
  - No creative from a held-out campaign leaks into training
  - Evaluation simulates real cold-start performance
  - The reported metrics are honest out-of-campaign generalization
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from sklearn.model_selection import GroupKFold

from src.features.build_dataset import get_feature_sets
from src.models.train import (
    compute_metrics,
    get_feature_importance,
    train_baseline,
    train_lightgbm,
)

logger = logging.getLogger(__name__)


def run_group_kfold_cv(
    df: pd.DataFrame,
    feature_cols: List[str],
    target_col: str,
    group_col: str,
    config: dict,
    model_name: str = "lightgbm",
) -> Dict:
    """Run GroupKFold cross-validation for a single model + feature set.

    Parameters
    ----------
    df : pd.DataFrame
        Full feature dataset.
    feature_cols : list of str
        Feature columns to use.
    target_col : str
        Target column name (e.g. 'engagement_rate').
    group_col : str
        Column to group by (default: 'campaign_id').
    config : dict
        Pipeline configuration.
    model_name : str
        'baseline' or 'lightgbm'.

    Returns
    -------
    dict with aggregated cross-validation metrics.
    """
    n_splits = config["modeling"]["n_splits"]
    random_seed = config["pipeline"]["random_seed"]

    # Drop rows where target or group is missing
    mask = df[target_col].notna() & df[group_col].notna()
    df_clean = df[mask].copy()

    if len(df_clean) < n_splits * 2:
        logger.warning(
            f"Not enough data for {n_splits}-fold CV on {target_col}: "
            f"{len(df_clean)} rows after filtering"
        )
        return {"error": "insufficient_data", "n_rows": len(df_clean)}

    X = df_clean[feature_cols].fillna(0)
    y = df_clean[target_col].values
    groups = df_clean[group_col].values

    gkf = GroupKFold(n_splits=n_splits)

    fold_metrics = []
    all_importances = {}

    for fold_idx, (train_idx, val_idx) in enumerate(gkf.split(X, y, groups)):
        X_train, X_val = X.iloc[train_idx], X.iloc[val_idx]
        y_train, y_val = y[train_idx], y[val_idx]

        # Train
        if model_name == "baseline":
            model = train_baseline(X_train, y_train)
        else:
            model = train_lightgbm(X_train, y_train, config)

        # Predict
        y_pred = model.predict(X_val)

        # Metrics
        metrics = compute_metrics(
            y_val,
            y_pred,
            target_name=f"{model_name} fold {fold_idx + 1}",
        )
        fold_metrics.append(metrics)

        # Feature importance
        fi = get_feature_importance(model, feature_cols)
        for feat, imp in fi.items():
            all_importances[feat] = all_importances.get(feat, 0) + imp

    # Aggregate across folds
    agg = {}
    for metric in ["mae", "rmse", "r2", "mape"]:
        values = [m[metric] for m in fold_metrics if metric in m]
        agg[f"{metric}_mean"] = float(np.mean(values))
        agg[f"{metric}_std"] = float(np.std(values))

    # Average feature importances
    if all_importances:
        agg["feature_importance"] = {
            k: v / n_splits
            for k, v in sorted(all_importances.items(), key=lambda x: x[1], reverse=True)
        }

    agg["n_folds"] = len(fold_metrics)
    agg["n_features"] = len(feature_cols)
    agg["n_train_campaigns"] = int(df_clean[group_col].nunique())

    return agg


def run_benchmark(
    feature_df: pd.DataFrame,
    config: dict,
    target_col: Optional[str] = None,
    force_recompute: bool = False,
) -> Dict:
    """Run the complete 4-way benchmark: Baseline vs Tabular vs Vision vs Multimodal.

    Parameters
    ----------
    feature_df : pd.DataFrame
        Full feature dataset from build_dataset.py
    config : dict
        Pipeline configuration.
    target_col : str, optional
        Which KPI to predict. Default from config.
    force_recompute : bool
        If True, recompute even if results exist.

    Returns
    -------
    dict
        Full benchmark results JSON with all model metrics.
    """
    results_path = Path(config["evaluation"]["results_path"])
    if results_path.exists() and not force_recompute:
        logger.info(f"Loading existing benchmark results from {results_path}")
        with open(results_path) as f:
            return json.load(f)

    results_path.parent.mkdir(parents=True, exist_ok=True)

    if target_col is None:
        target_col = config["modeling"]["primary_target"]

    group_col = config["modeling"]["group_col"]

    logger.info(
        f"\n{'='*60}\n"
        f"BENCHMARK: predicting '{target_col}' with GroupKFold(n={config['modeling']['n_splits']})\n"
        f"Grouped by: '{group_col}'\n"
        f"Dataset: {len(feature_df):,} rows, {feature_df[group_col].nunique()} campaigns\n"
        f"{'='*60}"
    )

    # Get feature sets
    feature_sets = get_feature_sets(feature_df)

    results = {
        "target": target_col,
        "group_col": group_col,
        "dataset_size": len(feature_df),
        "n_campaigns": int(feature_df[group_col].nunique()),
        "models": {},
    }

    # ── A: Baseline ─────────────────────────────────────────────────
    logger.info("\n[A] Baseline (Global Mean Predictor)")
    baseline_cols = feature_sets["tabular"][:1] if feature_sets["tabular"] else ["has_video"]
    results["models"]["baseline"] = run_group_kfold_cv(
        df=feature_df,
        feature_cols=baseline_cols,
        target_col=target_col,
        group_col=group_col,
        config=config,
        model_name="baseline",
    )

    # ── B: Tabular-Only ─────────────────────────────────────────────
    logger.info("\n[B] Tabular-Only (Campaign context + creative metadata)")
    if feature_sets["tabular"]:
        results["models"]["tabular"] = run_group_kfold_cv(
            df=feature_df,
            feature_cols=feature_sets["tabular"],
            target_col=target_col,
            group_col=group_col,
            config=config,
            model_name="lightgbm",
        )
    else:
        logger.warning("No tabular features available; skipping tabular model.")
        results["models"]["tabular"] = {"error": "no_features"}

    # ── C: Vision-Only ──────────────────────────────────────────────
    logger.info("\n[C] Vision-Only (ResNet50 embeddings + visual metrics)")
    if feature_sets["vision"]:
        results["models"]["vision"] = run_group_kfold_cv(
            df=feature_df,
            feature_cols=feature_sets["vision"],
            target_col=target_col,
            group_col=group_col,
            config=config,
            model_name="lightgbm",
        )
    else:
        logger.warning("No vision features available; skipping vision model.")
        results["models"]["vision"] = {"error": "no_features"}

    # ── D: Multimodal (Tabular + Vision) ────────────────────────────
    logger.info("\n[D] Multimodal (Tabular + Vision combined)")
    if feature_sets["multimodal"]:
        results["models"]["multimodal"] = run_group_kfold_cv(
            df=feature_df,
            feature_cols=feature_sets["multimodal"],
            target_col=target_col,
            group_col=group_col,
            config=config,
            model_name="lightgbm",
        )
    else:
        logger.warning("No multimodal features available.")
        results["models"]["multimodal"] = {"error": "no_features"}

    # ── Summary comparison table ─────────────────────────────────────
    logger.info("\n" + "=" * 60)
    logger.info(f"BENCHMARK RESULTS SUMMARY: {target_col}")
    logger.info("=" * 60)
    header = f"{'Model':<15} {'MAE':>8} {'RMSE':>8} {'R²':>8} {'MAPE':>8}"
    logger.info(header)
    logger.info("-" * 60)
    for model_name, model_results in results["models"].items():
        if "error" in model_results:
            logger.info(f"{model_name:<15} {'ERROR':>8}")
            continue
        mae = model_results.get("mae_mean", float("nan"))
        rmse = model_results.get("rmse_mean", float("nan"))
        r2 = model_results.get("r2_mean", float("nan"))
        mape = model_results.get("mape_mean", float("nan"))
        logger.info(
            f"{model_name:<15} {mae:>8.4f} {rmse:>8.4f} {r2:>8.4f} {mape:>8.2f}"
        )
    logger.info("=" * 60)

    # Save results
    with open(results_path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    logger.info(f"\nBenchmark results saved to {results_path}")

    return results
