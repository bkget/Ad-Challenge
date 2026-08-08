"""Data loading utilities for Ad-Challenge pipeline.

Responsibilities:
- Load raw CSV, JSON data files
- Validate column presence and data types  
- Return clean DataFrames/dicts ready for downstream processing
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Tuple, Any

import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


def load_briefing(path: str) -> pd.DataFrame:
    """Load and lightly clean the campaign briefing CSV.
    
    Parameters
    ----------
    path : str
        Path to briefing.csv
        
    Returns
    -------
    pd.DataFrame
        DataFrame with normalized column names and parsed dates.
    """
    logger.info(f"Loading briefing data from {path}")
    df = pd.read_csv(path, low_memory=False)
    
    # Normalize column names: lowercase, replace spaces & special chars with underscore
    df.columns = (
        df.columns
        .str.lower()
        .str.replace(r"[^a-z0-9]+", "_", regex=True)
        .str.strip("_")
    )
    
    # Keep only one row per campaign_id (latest submission)
    # The briefing CSV can have multiple rows per campaign_id (updates)
    df = df.sort_values("submission_date", ascending=False)
    df = df.drop_duplicates(subset="campaign_id", keep="first")
    
    # Parse date columns
    for col in ["startdate", "enddate"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], dayfirst=True, errors="coerce")
    
    # Fill missing numeric cols
    for col in ["buy_rate_cpe", "volume_agreed", "gross_cost_budget"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
    
    logger.info(f"Briefing loaded: {len(df)} unique campaigns")
    return df.reset_index(drop=True)


def load_inventory(path: str, chunksize: int = 500_000) -> pd.DataFrame:
    """Load the campaigns inventory (event log) CSV.
    
    This is a large file (~100MB). We read in chunks and concatenate.
    
    Parameters
    ----------
    path : str
        Path to campaigns_inventory_updated.csv
    chunksize : int
        Number of rows per chunk for memory-efficient loading
        
    Returns
    -------
    pd.DataFrame
        Full inventory DataFrame.
    """
    logger.info(f"Loading inventory data from {path} (chunksize={chunksize})")
    chunks = []
    for chunk in pd.read_csv(path, chunksize=chunksize, low_memory=False):
        # Normalize column names
        chunk.columns = (
            chunk.columns
            .str.lower()
            .str.replace(r"[^a-z0-9]+", "_", regex=True)
            .str.strip("_")
        )
        chunks.append(chunk)
    
    df = pd.concat(chunks, ignore_index=True)
    
    # Normalize event type values
    if "type" in df.columns:
        df["type"] = df["type"].str.strip().str.lower()
    
    # Parse browser_ts
    if "browser_ts" in df.columns:
        df["browser_ts"] = pd.to_datetime(df["browser_ts"], errors="coerce")
    
    logger.info(f"Inventory loaded: {len(df):,} events")
    return df


def load_global_design(path: str) -> Dict[str, Any]:
    """Load the global design JSON (creative metadata).
    
    Parameters
    ----------
    path : str
        Path to global_design_data.json
        
    Returns
    -------
    dict
        Nested dict: {game_key: {request_id: {labels, text, colors, videos_data, ...}}}
    """
    logger.info(f"Loading global design data from {path}")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    logger.info(f"Global design loaded: {len(data)} game_keys")
    return data


def load_image_features(path: str) -> List[Dict]:
    """Load the pre-extracted image features JSON.
    
    Parameters
    ----------
    path : str
        Path to image_features.json
        
    Returns
    -------
    list
        List of dicts with image feature records.
    """
    logger.info(f"Loading image features from {path}")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    logger.info(f"Image features loaded: {len(data)} records")
    return data


def list_creative_images(images_dir: str) -> pd.DataFrame:
    """Scan the Creative Assets directory and return a DataFrame of image metadata.
    
    Parameters
    ----------
    images_dir : str
        Path to the Creative Assets_ directory
        
    Returns
    -------
    pd.DataFrame
        DataFrame with columns: filename, filepath, slug, request_id, placement_type, file_size_kb
    """
    logger.info(f"Scanning creative images from {images_dir}")
    images_dir = Path(images_dir)
    
    records = []
    for img_path in sorted(images_dir.glob("*.png")):
        filename = img_path.stem  # filename without .png
        file_size_kb = img_path.stat().st_size / 1024
        
        # Parse filename: the last 20-char hex token is the request_id
        # Everything before is the slug (creative name)
        parts = filename.rsplit("-", 1)
        if len(parts) == 2 and len(parts[1]) == 20:
            slug = parts[0]        # e.g. adunit-iwc-portugieser-physics-mob
            request_id = parts[1]  # e.g. d071433c0e09216d8f80
        else:
            slug = filename
            request_id = None
        
        # Detect placement type from slug
        if "-mob" in slug or "-mob-" in slug:
            placement_type = "mobile"
        elif "-mpu" in slug or "-mpu-" in slug:
            placement_type = "mpu"
        elif "-tap" in slug:
            placement_type = "tap"
        elif "-bio" in slug:
            placement_type = "bio"
        else:
            placement_type = "unknown"
        
        records.append({
            "filename": img_path.name,
            "filepath": str(img_path),
            "slug": slug,
            "request_id": request_id,
            "placement_type": placement_type,
            "file_size_kb": round(file_size_kb, 2),
        })
    
    df = pd.DataFrame(records)
    logger.info(f"Found {len(df)} creative images")
    return df


def run_ingestion(config: dict) -> Tuple[pd.DataFrame, pd.DataFrame, Dict, List, pd.DataFrame]:
    """Run the complete ingestion step.
    
    Parameters
    ----------
    config : dict
        Pipeline configuration dictionary
        
    Returns
    -------
    tuple
        (briefing_df, inventory_df, design_dict, image_features_list, images_df)
    """
    cfg = config["ingestion"]
    briefing_df = load_briefing(cfg["briefing_csv"])
    inventory_df = load_inventory(cfg["inventory_csv"])
    design_dict = load_global_design(cfg["design_json"])
    image_features = load_image_features(cfg["image_features_json"])
    images_df = list_creative_images(cfg["images_dir"])
    
    return briefing_df, inventory_df, design_dict, image_features, images_df
