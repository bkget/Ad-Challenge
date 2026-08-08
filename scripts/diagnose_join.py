"""Deeper diagnostic: understand the actual data linking structure."""
import json
import pandas as pd
from src.ingestion.loader import list_creative_images, load_inventory

# Load inventory (sample)
inv = load_inventory('data/campaigns_inventory_updated.csv', chunksize=100000)
print(f"Inventory shape: {inv.shape}")
print(f"Inventory columns: {list(inv.columns)}")
print(f"Unique game_keys in inventory: {inv['game_key'].nunique()}")
print(f"Sample game_keys from inventory:")
print(inv['game_key'].value_counts().head(5))
print()

# Load design JSON and examine its keys
with open('data/global_design_data.json') as f:
    design = json.load(f)

design_keys = list(design.keys())
print(f"Design JSON top-level keys (game_keys): {len(design_keys)}")
print(f"Sample design game_keys: {design_keys[:5]}")
print()

# Check overlap between inventory game_keys and design JSON keys
inv_gk = set(inv['game_key'].dropna().astype(str))
design_gk = set(design_keys)
overlap_gk = inv_gk & design_gk
print(f"Inventory game_keys: {len(inv_gk)}")
print(f"Design game_keys: {len(design_gk)}")
print(f"game_key overlap: {len(overlap_gk)}")
print(f"Sample overlapping game_keys: {list(overlap_gk)[:3]}")
print()

# Examine what's INSIDE one design entry
sample_gk = list(design.keys())[0]
sample_entry = design[sample_gk]
print(f"Design entry for game_key '{sample_gk}':")
print(f"  Sub-keys (request_ids): {list(sample_entry.keys())[:3]}")
sample_rid = list(sample_entry.keys())[0]
sample_features = sample_entry[sample_rid]
print(f"  Feature keys for request_id '{sample_rid}': {list(sample_features.keys())}")
print()

# Check image_features.json
with open('data/image_features.json') as f:
    img_feats = json.load(f)
print(f"image_features.json: {len(img_feats)} records")
if img_feats:
    first = img_feats[0] if isinstance(img_feats, list) else img_feats
    print(f"Type: {type(img_feats)}")
    if isinstance(img_feats, list):
        print(f"First record keys: {list(img_feats[0].keys()) if img_feats else 'empty'}")
    elif isinstance(img_feats, dict):
        print(f"Top-level keys (sample): {list(img_feats.keys())[:3]}")
