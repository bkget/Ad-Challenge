"""Inference engine: predict creative performance for new ad creatives.

Given a new creative asset (image path + campaign context), this module:
1. Extracts visual features from the image
2. Applies saved PCA transformation
3. Looks up or provides campaign context features
4. Runs the trained multimodal model to predict ER% and CTR%
5. Returns a structured prediction result

This is the component that makes the demo interactive:
  - The web dashboard calls this with user-selected parameters
  - The API exposes this as a prediction endpoint
"""

import json
import logging
import pickle
from pathlib import Path
from typing import Dict, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def load_artifacts(models_dir: str, processed_dir: str) -> dict:
    """Load all saved model artifacts for inference.

    Parameters
    ----------
    models_dir : str
        Directory where trained models are saved.
    processed_dir : str
        Directory where PCA model is saved.

    Returns
    -------
    dict with keys: multimodal_model, encoders, pca_artifacts
    """
    artifacts = {}

    # Load multimodal LightGBM model
    model_path = Path(models_dir) / "multimodal.pkl"
    if model_path.exists():
        with open(model_path, "rb") as f:
            artifacts["multimodal_model"] = pickle.load(f)
    else:
        logger.warning(f"Multimodal model not found at {model_path}. Run training first.")
        artifacts["multimodal_model"] = None

    # Load encoders
    encoders_path = Path(models_dir) / "encoders.pkl"
    if encoders_path.exists():
        with open(encoders_path, "rb") as f:
            artifacts["encoders"] = pickle.load(f)
    else:
        artifacts["encoders"] = {}

    # Load PCA model
    pca_path = Path(processed_dir) / "pca_model.pkl"
    if pca_path.exists():
        with open(pca_path, "rb") as f:
            artifacts["pca_artifacts"] = pickle.load(f)
    else:
        logger.warning(f"PCA model not found at {pca_path}")
        artifacts["pca_artifacts"] = None

    return artifacts


def predict_creative_performance(
    image_path: Optional[str],
    context: Dict,
    artifacts: dict,
    config: dict,
) -> Dict:
    """Predict ER% and CTR% for a creative + campaign context.

    Parameters
    ----------
    image_path : str or None
        Path to the ad creative image. If None, uses tabular-only prediction.
    context : dict
        Campaign context features:
          - device_type: str (e.g., 'smartphone', 'tablet')
          - platform_os: str (e.g., 'iOS', 'Android')
          - geo_country: str (e.g., 'USA', 'SGP')
          - has_video: bool
          - buy_rate_cpe: float
          Optional: vision features dict if pre-computed
    artifacts : dict
        Loaded model artifacts from load_artifacts()
    config : dict
        Pipeline configuration.

    Returns
    -------
    dict with keys:
        engagement_rate_predicted: float (0-1)
        click_through_rate_predicted: float (0-1)
        confidence_note: str
        vision_features_used: bool
        feature_contributions: dict (top features driving prediction)
    """
    result = {
        "engagement_rate_predicted": None,
        "click_through_rate_predicted": None,
        "confidence_note": "",
        "vision_features_used": False,
        "feature_contributions": {},
    }

    model = artifacts.get("multimodal_model")
    if model is None:
        result["confidence_note"] = "Model not trained yet. Run pipeline first."
        return result

    # --- Build feature row ---
    feature_row = {}

    # Context features
    feature_row["device_type"] = context.get("device_type", "unknown")
    feature_row["platform_os"] = context.get("platform_os", "unknown")
    feature_row["geo_country"] = context.get("geo_country", "unknown")
    feature_row["has_video"] = int(context.get("has_video", 0))
    feature_row["buy_rate_cpe"] = float(context.get("buy_rate_cpe", 0.0))

    # Encode categoricals using saved encoders
    encoders = artifacts.get("encoders", {})
    for col in ["device_type", "platform_os", "geo_country"]:
        enc_col = col + "_enc"
        le = encoders.get(col)
        val = str(feature_row.get(col, "unknown"))
        if le is not None:
            known = set(le.classes_)
            if val not in known:
                val = "unknown"
            if val in known:
                feature_row[enc_col] = int(le.transform([val])[0])
            else:
                feature_row[enc_col] = 0
        else:
            feature_row[enc_col] = 0

    # Vision features
    if image_path is not None:
        try:
            from PIL import Image
            from src.vision.extractor import extract_handcrafted_features

            img = Image.open(image_path).convert("RGB")
            vis_feats = extract_handcrafted_features(img)
            feature_row.update(vis_feats)

            # Apply PCA if available
            pca_artifacts = artifacts.get("pca_artifacts")
            if pca_artifacts is not None:
                from src.vision.extractor import extract_deep_embeddings

                emb = extract_deep_embeddings([image_path], batch_size=1)
                scaler = pca_artifacts["scaler"]
                pca = pca_artifacts["pca"]
                emb_scaled = scaler.transform(emb)
                emb_pca = pca.transform(emb_scaled)

                for i, val in enumerate(emb_pca[0]):
                    feature_row[f"vision_pca_{i}"] = float(val)

            result["vision_features_used"] = True
            logger.info(f"Vision features extracted from {image_path}")

        except Exception as e:
            logger.warning(f"Vision extraction failed for {image_path}: {e}")
            result["confidence_note"] = f"Vision extraction failed: {e}. Using tabular-only."

    # Build DataFrame for model
    row_df = pd.DataFrame([feature_row])

    # Fill missing feature columns with 0
    expected_cols = getattr(model, "feature_name_", None)
    if expected_cols is not None:
        for col in expected_cols:
            if col not in row_df.columns:
                row_df[col] = 0.0
        row_df = row_df[expected_cols]

    row_df = row_df.fillna(0.0)

    try:
        er_pred = float(model.predict(row_df)[0])
        er_pred = max(0.0, min(1.0, er_pred))  # Clip to [0, 1]
    except Exception as e:
        logger.error(f"Model prediction failed: {e}")
        er_pred = None

    result["engagement_rate_predicted"] = er_pred

    # For CTR, load separate CTR model if available, else use ER * 0.1 heuristic
    ctr_model_path = Path(config["pipeline"]["models_dir"]) / "multimodal_ctr.pkl"
    if ctr_model_path.exists():
        with open(ctr_model_path, "rb") as f:
            ctr_model = pickle.load(f)
        try:
            ctr_pred = float(ctr_model.predict(row_df)[0])
            ctr_pred = max(0.0, min(1.0, ctr_pred))
        except Exception:
            ctr_pred = er_pred * 0.1 if er_pred else 0.0
    else:
        ctr_pred = er_pred * 0.1 if er_pred else 0.0

    result["click_through_rate_predicted"] = ctr_pred

    if not result["confidence_note"]:
        result["confidence_note"] = (
            "Prediction from multimodal model (tabular + vision)" if result["vision_features_used"]
            else "Prediction from tabular-only model (no image provided)"
        )

    return result
