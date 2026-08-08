"""Entity resolution: linking images, design metadata, and inventory logs.

Key discovery from data exploration:
  The inventory `game_key` column has format: "<creative_slug>/<request_id>"
  e.g. "adunit-lionsgate-spiral-new-2-puzzle-v3-mpu/6dd6706b4dc812c36e40"

  The Creative Assets_ image filenames have format: "<creative_slug>-<request_id>.png"
  e.g. "adunit-lionsgate-spiral-new-2-puzzle-v3-mpu-6dd6706b4dc812c36e40.png"

  The slug (creative name) and request_id BOTH appear in both — this is the link.
  The global_design_data.json uses MD5 hashes as game_keys (different namespace,
  useful for creative metadata but NOT for linking to inventory).

Resolution strategy:
  1. Parse slug + request_id from inventory game_key (split on last '/')
  2. Build image-to-inventory join via (slug, request_id) matching
  3. Join design metadata via slug prefix matching
  4. Compute ER/CTR per (campaign_id, game_key, context) grain
"""

import logging
from pathlib import Path
from typing import Dict, List, Any, Optional

import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


def parse_game_key(game_key: str):
    """Parse a game_key of format '<slug>/<request_id>' into (slug, request_id).

    Parameters
    ----------
    game_key : str
        e.g. 'adunit-lionsgate-spiral-new-2-puzzle-v3-mpu/6dd6706b4dc812c36e40'

    Returns
    -------
    tuple (slug, request_id) or (game_key, None) if unparseable
    """
    if not isinstance(game_key, str):
        return (game_key, None)
    if '/' in game_key:
        parts = game_key.rsplit('/', 1)
        return (parts[0], parts[1])
    return (game_key, None)


def flatten_global_design(design_dict: Dict[str, Any]) -> pd.DataFrame:
    """Flatten the nested global_design_data.json into a tabular format.
    
    Structure: {game_key -> {request_id -> {labels, text, colors, videos_data, direction}}}
    
    Parameters
    ----------
    design_dict : dict
        The loaded global_design_data.json
        
    Returns
    -------
    pd.DataFrame
        One row per (game_key, request_id) with extracted features.
    """
    records = []
    for game_key, requests in design_dict.items():
        if not isinstance(requests, dict):
            continue
        for request_id, features in requests.items():
            if not isinstance(features, dict):
                continue
            
            # Extract engagement labels
            labels = features.get("labels", {})
            eng_labels = labels.get("engagement", [])
            ct_labels = labels.get("click_through", [])
            
            # Extract text features
            text = features.get("text", {})
            eng_text = text.get("engagement", [])
            ct_text = text.get("click_through", [])
            
            # Extract color features for engagement zone (top 3 colors)
            colors = features.get("colors", {})
            eng_colors = colors.get("engagement", {})
            
            # Get dominant color stats
            dominant_r, dominant_g, dominant_b = 0.0, 0.0, 0.0
            dominant_proportion = 0.0
            color_saturation_mean = 0.0
            color_luminosity_mean = 0.0
            color_diversity = 0  # Number of distinct color clusters
            
            if isinstance(eng_colors, dict) and eng_colors:
                color_diversity = len(eng_colors)
                # Top color by proportion
                if "1" in eng_colors:
                    c1 = eng_colors["1"]
                    dominant_r = c1.get("red", 0) / 255.0
                    dominant_g = c1.get("green", 0) / 255.0
                    dominant_b = c1.get("blue", 0) / 255.0
                    dominant_proportion = c1.get("proportion", 0.0)
                    
                # Mean saturation and luminosity across all colors
                sats = [v.get("saturation", 0) for v in eng_colors.values() if isinstance(v, dict)]
                lums = [v.get("luminosity", 0) for v in eng_colors.values() if isinstance(v, dict)]
                color_saturation_mean = np.mean(sats) if sats else 0.0
                color_luminosity_mean = np.mean(lums) if lums else 0.0
            
            # Video features
            videos = features.get("videos_data", {})
            has_video = int(videos.get("has_video", 0))
            video_length = 0.0
            if has_video and "videos_length" in videos:
                lengths = list(videos["videos_length"].values())
                video_length = np.mean(lengths) if lengths else 0.0
            
            # Direction of interaction
            direction = features.get("direction", {}).get("direction", "no direction")
            
            # Adunit sizes
            adunit_sizes = features.get("adunit_sizes", {})
            adunit_w = adunit_sizes.get("size_x", 0)
            adunit_h = adunit_sizes.get("size_y", 0)
            aspect_ratio = adunit_w / adunit_h if adunit_h > 0 else 0.0
            
            records.append({
                "game_key": game_key,
                "request_id": request_id,
                # Label features
                "n_engagement_labels": len(eng_labels),
                "n_click_through_labels": len(ct_labels),
                "engagement_labels_text": " ".join(eng_labels),
                # Text features
                "n_engagement_texts": len(eng_text),
                "n_click_through_texts": len(ct_text),
                "engagement_text_content": " ".join(eng_text) if eng_text else "",
                # Color features
                "dominant_color_r": dominant_r,
                "dominant_color_g": dominant_g,
                "dominant_color_b": dominant_b,
                "dominant_color_proportion": dominant_proportion,
                "color_saturation_mean": color_saturation_mean,
                "color_luminosity_mean": color_luminosity_mean,
                "color_diversity": color_diversity,
                # Brightness proxy (luminosity of dominant color)
                "brightness": (dominant_r + dominant_g + dominant_b) / 3.0,
                # Video
                "has_video": has_video,
                "video_length_seconds": video_length,
                # Interaction
                "interaction_direction": direction,
                # Layout
                "adunit_width": adunit_w,
                "adunit_height": adunit_h,
                "aspect_ratio": aspect_ratio,
            })
    
    df = pd.DataFrame(records)
    logger.info(f"Flattened global design: {len(df)} (game_key, request_id) records from {df['game_key'].nunique()} unique game_keys")
    return df


def resolve_images_to_design(
    images_df: pd.DataFrame,
    design_flat_df: pd.DataFrame
) -> pd.DataFrame:
    """Join Creative Assets images to their design metadata via request_id.
    
    Parameters
    ----------
    images_df : pd.DataFrame
        From loader.list_creative_images()
    design_flat_df : pd.DataFrame
        From flatten_global_design()
        
    Returns
    -------
    pd.DataFrame
        Joined image records with design metadata and visual feature placeholders.
    """
    # Match images to design records by request_id
    merged = images_df.merge(
        design_flat_df,
        on="request_id",
        how="left"
    )
    matched = merged["game_key"].notna().sum()
    logger.info(
        f"Image-to-design matching: {matched}/{len(images_df)} images matched "
        f"({matched/len(images_df)*100:.1f}%)"
    )
    return merged


def build_creative_kpi_table(
    inventory_df: pd.DataFrame,
    min_impressions: int = 10
) -> pd.DataFrame:
    """Build per-creative KPI table (ER%, CTR%) from raw inventory event logs.

    The inventory `game_key` has format: '<slug>/<request_id>'.
    We parse both components and compute KPIs at the
    (campaign_id, game_key, slug, request_id, device_type, platform_os, geo_country) grain.

    Parameters
    ----------
    inventory_df : pd.DataFrame
        Raw event log DataFrame
    min_impressions : int
        Minimum number of impression events required to include a row

    Returns
    -------
    pd.DataFrame
        One row per (campaign_id, game_key, context) with ER, CTR, slug, request_id.
    """
    logger.info("Building creative KPI table from inventory events...")

    # Parse slug and request_id from game_key
    df = inventory_df.copy()
    parsed = df['game_key'].apply(parse_game_key)
    df['creative_slug'] = parsed.apply(lambda x: x[0])
    df['creative_request_id'] = parsed.apply(lambda x: x[1])

    # Define context columns for grouping
    group_cols = [
        'campaign_id', 'game_key', 'creative_slug', 'creative_request_id',
        'device_type', 'platform_os', 'geo_country'
    ]
    available = [c for c in group_cols if c in df.columns]

    # Pivot event type counts
    event_counts = (
        df
        .groupby(available + ['type'])
        .size()
        .unstack(fill_value=0)
        .reset_index()
    )

    # Normalize event type column names
    event_counts.columns.name = None
    col_rename = {}
    for col in event_counts.columns:
        col_str = str(col)
        if col_str == 'impression':
            col_rename[col] = 'n_impressions'
        elif col_str == 'first_dropped':
            col_rename[col] = 'n_engagements'
        elif col_str == 'click-through-event':
            col_rename[col] = 'n_clicks'
    event_counts = event_counts.rename(columns=col_rename)

    for col in ['n_impressions', 'n_engagements', 'n_clicks']:
        if col not in event_counts.columns:
            event_counts[col] = 0

    # Filter rows with enough impressions
    kpi_df = event_counts[event_counts['n_impressions'] >= min_impressions].copy()

    # Compute KPI targets
    kpi_df['engagement_rate'] = (
        kpi_df['n_engagements'] / kpi_df['n_impressions']
    ).clip(0, 1)

    kpi_df['click_through_rate'] = (
        kpi_df['n_clicks'] / kpi_df['n_impressions']
    ).clip(0, 1)

    logger.info(
        f"KPI table built: {len(kpi_df):,} rows "
        f"(campaigns={kpi_df['campaign_id'].nunique()}, "
        f"game_keys={kpi_df['game_key'].nunique()}, "
        f"slugs={kpi_df['creative_slug'].nunique()})"
    )
    logger.info(
        f"ER stats:  mean={kpi_df['engagement_rate'].mean():.4f}, "
        f"std={kpi_df['engagement_rate'].std():.4f}"
    )
    logger.info(
        f"CTR stats: mean={kpi_df['click_through_rate'].mean():.4f}, "
        f"std={kpi_df['click_through_rate'].std():.4f}"
    )

    return kpi_df.reset_index(drop=True)


def build_linked_dataset(
    kpi_df: pd.DataFrame,
    design_flat_df: pd.DataFrame,
    briefing_df: pd.DataFrame,
) -> pd.DataFrame:
    """Join KPI targets with creative design features and campaign context.

    Linking strategy:
      - kpi_df has creative_request_id parsed from game_key (slug/request_id)
      - design_flat_df has request_id from global_design_data.json
      - These request_ids ARE the same values — join on that
      - If no match, fall back to zero-filling design features

    Parameters
    ----------
    kpi_df : pd.DataFrame
        Per-creative KPI targets from build_creative_kpi_table()
    design_flat_df : pd.DataFrame
        Flattened creative design features from flatten_global_design()
    briefing_df : pd.DataFrame
        Campaign briefing metadata from load_briefing()

    Returns
    -------
    pd.DataFrame
        Linked dataset ready for feature engineering.
    """
    logger.info("Building linked dataset...")

    # Join KPIs with design features on request_id
    # kpi_df.creative_request_id == design_flat_df.request_id
    df = kpi_df.merge(
        design_flat_df.rename(columns={'request_id': 'creative_request_id'}),
        on='creative_request_id',
        how='left'
    )

    matched = df['color_saturation_mean'].notna().sum()
    logger.info(
        f"KPI-to-design matching: {matched}/{len(df)} rows matched design metadata "
        f"({matched/len(df)*100:.1f}%)"
    )

    # Join with briefing on campaign_id
    briefing_cols = [
        'campaign_id', 'campaign_name', 'campaign_objectives',
        'kpis', 'startdate', 'enddate',
        'currency', 'buy_rate_cpe', 'volume_agreed', 'gross_cost_budget'
    ]
    available_briefing_cols = [c for c in briefing_cols if c in briefing_df.columns]

    df = df.merge(
        briefing_df[available_briefing_cols],
        on='campaign_id',
        how='left'
    )

    # Compute campaign duration in days
    if 'startdate' in df.columns and 'enddate' in df.columns:
        df['campaign_duration_days'] = (
            df['enddate'] - df['startdate']
        ).dt.days.clip(0)

    # Add image_path column: reconstruct from slug + request_id for vision join
    # image filename format: <slug>-<request_id>.png
    df['image_filename'] = (
        df['creative_slug'].fillna('') + '-' +
        df['creative_request_id'].fillna('') + '.png'
    )

    logger.info(
        f"Linked dataset: {len(df):,} rows, "
        f"{df.shape[1]} columns, "
        f"{df['campaign_id'].nunique()} campaigns"
    )
    return df
