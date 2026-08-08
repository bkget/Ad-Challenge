"""Model training for creative performance prediction.

Implements four model configurations for the benchmark:
  1. Baseline     - Global mean predictor (DummyRegressor)
  2. Tabular      - LightGBM on campaign context + creative metadata
  3. Vision       - LightGBM on ResNet50 PCA embeddings + handcrafted visual features
  4. Multimodal   - LightGBM on tabular + vision features (all combined)

Design decision: LightGBM chosen over XGBoost/CatBoost because:
  - Handles mixed numeric/categorical features natively (with encoded cats)
  - Fast training on CPU for personal demo
  - Strong feature importance output for interview explainability
  - Comparable accuracy to neural approaches on small tabular datasets

Ridge Regression is added as an interpretable linear baseline
to demonstrate whether the signal is linear or requires non-linear modeling.
"""

import json
import logging
import pickle
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from sklearn.dummy import DummyRegressor
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.preprocessing import StandardScaler

logger = logging.getLogger(__name__)


def mean_absolute_percentage_error(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Compute MAPE, handling zero denominators gracefully."""
    mask = y_true != 0
    if mask.sum() == 0:
        return float("nan")
    return float(np.mean(np.abs((y_true[mask] - y_pred[mask]) / y_true[mask])) * 100)


def compute_metrics(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    target_name: str = "target",
) -> Dict[str, float]:
    """Compute regression evaluation metrics.

    Parameters
    ----------
    y_true : array-like
    y_pred : array-like
    target_name : str
        Label for logging.

    Returns
    -------
    dict with keys: mae, rmse, r2, mape
    """
    y_true = np.array(y_true, dtype=float)
    y_pred = np.clip(np.array(y_pred, dtype=float), 0, None)

    mae = mean_absolute_error(y_true, y_pred)
    rmse = float(np.sqrt(mean_squared_error(y_true, y_pred)))
    r2 = r2_score(y_true, y_pred)
    mape = mean_absolute_percentage_error(y_true, y_pred)

    logger.info(
        f"[{target_name}] MAE={mae:.4f} | RMSE={rmse:.4f} | R²={r2:.4f} | MAPE={mape:.2f}%"
    )
    return {"mae": mae, "rmse": rmse, "r2": r2, "mape": mape}


def train_baseline(
    X_train: pd.DataFrame,
    y_train: pd.Series,
) -> DummyRegressor:
    """Train a global mean baseline (DummyRegressor)."""
    model = DummyRegressor(strategy="mean")
    model.fit(X_train, y_train)
    return model


def train_lightgbm(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    config: dict,
) -> Any:
    """Train a LightGBM regressor.

    Parameters
    ----------
    X_train : pd.DataFrame
    y_train : pd.Series
    config : dict
        Pipeline config (uses modeling.lightgbm hyperparameters)

    Returns
    -------
    LGBMRegressor
    """
    try:
        from lightgbm import LGBMRegressor
    except ImportError:
        logger.error("LightGBM not installed. Run: pip install lightgbm")
        raise

    lgbm_cfg = config["modeling"]["lightgbm"]
    random_seed = config["pipeline"]["random_seed"]

    model = LGBMRegressor(
        n_estimators=lgbm_cfg.get("n_estimators", 300),
        learning_rate=lgbm_cfg.get("learning_rate", 0.05),
        max_depth=lgbm_cfg.get("max_depth", 6),
        num_leaves=lgbm_cfg.get("num_leaves", 31),
        min_child_samples=lgbm_cfg.get("min_child_samples", 10),
        subsample=lgbm_cfg.get("subsample", 0.8),
        colsample_bytree=lgbm_cfg.get("colsample_bytree", 0.8),
        reg_alpha=lgbm_cfg.get("reg_alpha", 0.1),
        reg_lambda=lgbm_cfg.get("reg_lambda", 0.1),
        random_state=random_seed,
        verbose=-1,
        n_jobs=-1,
    )

    model.fit(
        X_train,
        y_train,
        callbacks=None,
    )
    return model


def train_ridge(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    config: dict,
) -> Tuple[StandardScaler, Ridge]:
    """Train a Ridge regression model with standard scaling."""
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X_train.fillna(0))

    alpha = config["modeling"]["ridge"]["alpha"]
    model = Ridge(alpha=alpha)
    model.fit(X_scaled, y_train)

    return scaler, model


def get_feature_importance(model: Any, feature_names: List[str]) -> Dict[str, float]:
    """Extract feature importance from a trained model.

    Works for LightGBM (has feature_importances_) and Ridge (uses abs coef).
    """
    if hasattr(model, "feature_importances_"):
        importances = model.feature_importances_
    elif hasattr(model, "coef_"):
        importances = np.abs(model.coef_)
    else:
        return {}

    if len(importances) != len(feature_names):
        return {}

    return dict(
        sorted(
            zip(feature_names, importances.tolist()),
            key=lambda x: x[1],
            reverse=True,
        )
    )


def save_model(model: Any, path: str, model_name: str) -> None:
    """Persist a trained model to disk."""
    model_path = Path(path) / f"{model_name}.pkl"
    model_path.parent.mkdir(parents=True, exist_ok=True)
    with open(model_path, "wb") as f:
        pickle.dump(model, f)
    logger.info(f"Model saved: {model_path}")


def load_model(path: str) -> Any:
    """Load a persisted model from disk."""
    with open(path, "rb") as f:
        return pickle.load(f)
