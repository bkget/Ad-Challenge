"""Feature engineering and training dataset construction.

Responsibilities:
- Encode categorical context features
- Merge creative design features, KPI targets, and vision embeddings
- Produce a clean, ML-ready feature matrix
- Handle missing values and feature scaling

No data leakage: All aggregation and encoding fits on training data.
"""

import logging
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np
import pandas as pd
from sklearn.preprocessing import LabelEncoder, StandardScaler

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────
# Feature definitions
# ──────────────────────────────────────────────────────────

CONTEXT_CATEGORICAL_COLS = [
    "device_type",
    "platform_os",
    "geo_country",
    "interaction_direction",
]

CONTEXT_NUMERIC_COLS = [
    "has_video",
    "video_length_seconds",
    "n_engagement_labels",
    "n_click_through_labels",
    "n_engagement_texts",
    "n_click_through_texts",
    "dominant_color_r",
    "dominant_color_g",
    "dominant_color_b",
    "dominant_color_proportion",
    "color_saturation_mean",
    "color_luminosity_mean",
    "color_diversity",
    "brightness",
    "aspect_ratio",
]

CAMPAIGN_NUMERIC_COLS = [
    "buy_rate_cpe",
    "volume_agreed",
    "gross_cost_budget",
    "campaign_duration_days",
]

VISION_PCA_PREFIX = "vision_pca_"
HANDCRAFTED_VISION_COLS = [
    "brightness_mean",
    "saturation_mean",
    "colorfulness",
    "visual_entropy",
    "color_diversity_score",
    "is_dark_background",
    "is_light_background",
    "file_size_kb",
]


def encode_categoricals(
    df: pd.DataFrame,
    categorical_cols: List[str],
    encoders: Optional[dict] = None,
    fit: bool = True,
) -> Tuple[pd.DataFrame, dict]:
    """Encode categorical columns using LabelEncoder.

    Parameters
    ----------
    df : pd.DataFrame
        Input DataFrame.
    categorical_cols : list of str
        Column names to encode.
    encoders : dict, optional
        Pre-fitted encoders (for inference / test sets).
    fit : bool
        If True, fit new encoders on this data.

    Returns
    -------
    tuple
        (encoded_df, encoders_dict)
    """
    df = df.copy()
    if encoders is None:
        encoders = {}

    for col in categorical_cols:
        if col not in df.columns:
            df[col] = "unknown"
            continue

        df[col] = df[col].fillna("unknown").astype(str)

        if fit:
            le = LabelEncoder()
            df[col + "_enc"] = le.fit_transform(df[col])
            encoders[col] = le
        else:
            le = encoders.get(col)
            if le is None:
                df[col + "_enc"] = 0
            else:
                # Handle unseen categories gracefully
                known = set(le.classes_)
                df[col] = df[col].apply(lambda x: x if x in known else "unknown")
                if "unknown" not in known:
                    le.classes_ = np.append(le.classes_, "unknown")
                df[col + "_enc"] = le.transform(df[col])

    return df, encoders


def select_tabular_features(df: pd.DataFrame) -> List[str]:
    """Return list of tabular feature column names available in df."""
    # Encoded categoricals
    cat_enc = [c + "_enc" for c in CONTEXT_CATEGORICAL_COLS if c + "_enc" in df.columns]

    # Numeric context features
    ctx_num = [c for c in CONTEXT_NUMERIC_COLS if c in df.columns]

    # Campaign numeric
    camp_num = [c for c in CAMPAIGN_NUMERIC_COLS if c in df.columns]

    return cat_enc + ctx_num + camp_num


def select_vision_features(df: pd.DataFrame, use_pca: bool = True) -> List[str]:
    """Return list of vision feature column names available in df."""
    features = []

    # Handcrafted features
    features += [c for c in HANDCRAFTED_VISION_COLS if c in df.columns]

    if use_pca:
        # PCA embedding columns
        pca_cols = [c for c in df.columns if c.startswith(VISION_PCA_PREFIX)]
        features += sorted(pca_cols)

    return features


def build_feature_matrix(
    linked_df: pd.DataFrame,
    vision_df: Optional[pd.DataFrame],
    config: dict,
    encoders: Optional[dict] = None,
    fit: bool = True,
) -> Tuple[pd.DataFrame, dict]:
    """Build the complete feature matrix by joining all feature sources.

    Parameters
    ----------
    linked_df : pd.DataFrame
        Output of entity_resolution.build_linked_dataset()
    vision_df : pd.DataFrame or None
        Output of vision.extractor.run_vision_extraction()
    config : dict
        Pipeline configuration.
    encoders : dict, optional
        Pre-fitted encoders (pass for test/inference sets).
    fit : bool
        Whether to fit encoders.

    Returns
    -------
    tuple
        (feature_df, encoders_dict)
        feature_df has all features + targets + group/id columns
    """
    logger.info("Building feature matrix...")

    df = linked_df.copy()

    # Join vision features on image_filename
    # linked_df has 'image_filename' = slug-request_id.png
    # vision_df has 'filename' = slug-request_id.png
    if vision_df is not None and 'image_filename' in df.columns:
        vision_dedup = vision_df.copy()
        vision_dedup = vision_dedup.rename(columns={'filename': 'image_filename'})
        vision_dedup = vision_dedup.drop_duplicates(subset='image_filename', keep='first')

        # Only merge columns that don't already exist in df
        vision_merge_cols = ['image_filename'] + [
            c for c in vision_dedup.columns
            if c not in df.columns and c not in ('slug', 'request_id', 'filepath')
        ]
        available_vision_cols = [c for c in vision_merge_cols if c in vision_dedup.columns]

        df = df.merge(
            vision_dedup[available_vision_cols],
            on='image_filename',
            how='left',
        )
        matched = df[HANDCRAFTED_VISION_COLS[0]].notna().sum() if HANDCRAFTED_VISION_COLS[0] in df.columns else 0
        total = len(df)
        logger.info(
            f"Vision features merged: {matched}/{total} rows matched image data "
            f"({matched/total*100:.1f}%)"
        )
    elif vision_df is not None:
        logger.warning("'image_filename' column not found in linked_df; skipping vision join.")

    # Encode categorical columns
    df, encoders = encode_categoricals(
        df,
        CONTEXT_CATEGORICAL_COLS,
        encoders=encoders,
        fit=fit,
    )

    # Fill missing numerics with median (suppress warnings for all-NaN columns)
    all_numeric = select_tabular_features(df) + select_vision_features(df)
    import warnings
    for col in all_numeric:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
            if fit:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", RuntimeWarning)
                    fill_val = df[col].median()
                fill_val = 0.0 if pd.isna(fill_val) else float(fill_val)
                df[col] = df[col].fillna(fill_val)
            else:
                df[col] = df[col].fillna(0.0)


    logger.info(
        f"Feature matrix built: {len(df):,} rows, "
        f"{df.shape[1]} total columns"
    )
    return df, encoders


def get_feature_sets(df: pd.DataFrame) -> dict:
    """Return the feature column sets for each model type.

    Returns
    -------
    dict with keys:
        'tabular': list of tabular feature columns
        'vision': list of vision feature columns
        'multimodal': combined tabular + vision
    """
    tabular = select_tabular_features(df)
    vision = select_vision_features(df)
    multimodal = list(dict.fromkeys(tabular + vision))  # Deduplicated, ordered

    return {
        "tabular": tabular,
        "vision": vision,
        "multimodal": multimodal,
    }


def run_feature_engineering(
    linked_df: pd.DataFrame,
    vision_df: Optional[pd.DataFrame],
    config: dict,
    force_recompute: bool = False,
) -> pd.DataFrame:
    """Run the complete feature engineering stage.

    Parameters
    ----------
    linked_df : pd.DataFrame
        Linked dataset from entity resolution
    vision_df : pd.DataFrame or None
        Vision features from extractor
    config : dict
        Pipeline configuration
    force_recompute : bool
        If True, recompute even if cache exists

    Returns
    -------
    pd.DataFrame
        Feature dataset ready for training.
    """
    cache_path = Path(config["features"]["feature_cache_path"])

    if cache_path.exists() and not force_recompute:
        logger.info(f"Loading feature dataset from cache: {cache_path}")
        return pd.read_parquet(cache_path)

    cache_path.parent.mkdir(parents=True, exist_ok=True)

    feature_df, _ = build_feature_matrix(
        linked_df=linked_df,
        vision_df=vision_df,
        config=config,
        fit=True,
    )

    feature_df.to_parquet(cache_path, index=False)
    logger.info(f"Feature dataset saved to {cache_path}")

    return feature_df
