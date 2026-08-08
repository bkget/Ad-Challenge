"""Vision feature extraction for ad creative images.

Extracts:
1. Deep ResNet50 embeddings (2048-dim) -> PCA reduced to 32-dim
2. Handcrafted visual features:
   - Mean brightness (L channel in LAB)
   - Mean saturation (S channel in HSV)
   - Visual entropy (image complexity measure)
   - Aspect ratio (W/H)
   - Color diversity (number of distinct color clusters in k-means, k=5)
   - Colorfulness score (Hasler & Susstrunk 2003)

Design decisions:
- Uses torchvision ResNet50 pretrained on ImageNet (no fine-tuning needed for interview demo)
- CPU-only inference to avoid CUDA setup friction on personal machines
- Caches results to parquet to avoid re-extraction on pipeline reruns
- PCA is fit ONLY on training data to prevent leakage; inference uses saved PCA model
"""

import logging
import pickle
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from PIL import Image
from tqdm import tqdm

logger = logging.getLogger(__name__)

# Lazy imports for torch to allow the module to be imported without torch
_torch = None
_torchvision = None
_transforms = None


def _get_torch():
    """Lazy-load PyTorch to avoid import errors if not installed."""
    global _torch, _torchvision, _transforms
    if _torch is None:
        import torch
        import torchvision.models as models
        import torchvision.transforms as transforms
        _torch = torch
        _torchvision = models
        _transforms = transforms
    return _torch, _torchvision, _transforms


def _get_resnet50_model():
    """Load pretrained ResNet50 as a feature extractor (remove final FC layer)."""
    torch, models, transforms = _get_torch()
    
    # Load pretrained weights
    model = models.resnet50(weights=models.ResNet50_Weights.IMAGENET1K_V2)
    
    # Remove the final classification layer to get 2048-dim feature vectors
    # We use avgpool output: (batch, 2048, 1, 1) -> squeeze -> (batch, 2048)
    model = torch.nn.Sequential(*list(model.children())[:-1])
    model.eval()
    
    return model


def _get_image_transforms(image_size: int = 224):
    """Build standard ImageNet preprocessing transforms."""
    _, _, transforms = _get_torch()
    return transforms.Compose([
        transforms.Resize((image_size, image_size)),
        transforms.ToTensor(),
        transforms.Normalize(
            mean=[0.485, 0.456, 0.406],  # ImageNet means
            std=[0.229, 0.224, 0.225]    # ImageNet stds
        ),
    ])


def extract_handcrafted_features(img: Image.Image) -> Dict[str, float]:
    """Extract handcrafted visual features from a PIL image.
    
    Parameters
    ----------
    img : PIL.Image.Image
        RGB image
        
    Returns
    -------
    dict
        Dictionary of feature_name -> float value
    """
    # Ensure RGB
    img_rgb = img.convert("RGB")
    w, h = img_rgb.size
    
    # Aspect ratio
    aspect_ratio = w / h if h > 0 else 1.0
    
    # Convert to numpy
    arr = np.array(img_rgb, dtype=np.float32) / 255.0  # Shape: (H, W, 3)
    
    # --- Brightness (mean luminance via weighted RGB) ---
    # Using ITU-R BT.709 luminance weights
    brightness = (
        0.2126 * arr[:, :, 0] +
        0.7152 * arr[:, :, 1] +
        0.0722 * arr[:, :, 2]
    ).mean()
    
    # --- Saturation (using HSV) ---
    r, g, b = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2]
    cmax = np.maximum(np.maximum(r, g), b)
    cmin = np.minimum(np.minimum(r, g), b)
    delta = cmax - cmin
    # Saturation: delta / cmax (avoid division by zero)
    with np.errstate(divide="ignore", invalid="ignore"):
        saturation = np.where(cmax > 0, delta / cmax, 0.0)
    mean_saturation = saturation.mean()
    
    # --- Colorfulness score (Hasler & Susstrunk 2003) ---
    rg = r - g
    yb = 0.5 * (r + g) - b
    std_rg = rg.std()
    std_yb = yb.std()
    mean_rg = abs(rg.mean())
    mean_yb = abs(yb.mean())
    colorfulness = (
        np.sqrt(std_rg**2 + std_yb**2) +
        0.3 * np.sqrt(mean_rg**2 + mean_yb**2)
    )
    
    # --- Visual entropy (image complexity) ---
    # Compute grayscale histogram entropy
    gray = np.array(img_rgb.convert("L"), dtype=np.float32)
    hist, _ = np.histogram(gray.flatten(), bins=256, range=(0, 256))
    hist_norm = hist / (hist.sum() + 1e-9)
    entropy = -np.sum(hist_norm * np.log2(hist_norm + 1e-9))
    
    # --- Color diversity (dominant color clusters) ---
    # Downsample for speed, cluster pixels into 5 groups
    small = img_rgb.resize((64, 64))
    pixels = np.array(small, dtype=np.float32).reshape(-1, 3) / 255.0
    # Simple: count pixels in 8 equal RGB quantization buckets
    quantized = (pixels * 4).astype(int).clip(0, 3)  # 4^3 = 64 buckets
    bucket_ids = quantized[:, 0] * 16 + quantized[:, 1] * 4 + quantized[:, 2]
    n_unique_buckets = len(np.unique(bucket_ids))
    color_diversity_score = n_unique_buckets / 64.0  # Normalize to [0, 1]
    
    # --- Dark/light background detection ---
    is_dark_bg = float(brightness < 0.3)
    is_light_bg = float(brightness > 0.7)
    
    return {
        "aspect_ratio": float(aspect_ratio),
        "image_width": float(w),
        "image_height": float(h),
        "brightness_mean": float(brightness),
        "saturation_mean": float(mean_saturation),
        "colorfulness": float(colorfulness),
        "visual_entropy": float(entropy),
        "color_diversity_score": float(color_diversity_score),
        "is_dark_background": is_dark_bg,
        "is_light_background": is_light_bg,
        # NOTE: file_size_kb is NOT included here — it is added by the caller
        # from images_df to avoid duplicate columns in the result DataFrame.
    }


def extract_deep_embeddings(
    image_paths: List[str],
    batch_size: int = 16,
    image_size: int = 224,
) -> np.ndarray:
    """Extract ResNet50 deep embeddings for a list of image paths.
    
    Parameters
    ----------
    image_paths : list of str
        Absolute paths to PNG images
    batch_size : int
        Number of images per inference batch
    image_size : int
        Resize target (default 224 for ResNet50)
        
    Returns
    -------
    np.ndarray
        Shape (N, 2048) array of embedding vectors
    """
    torch, _, _ = _get_torch()
    model = _get_resnet50_model()
    transform = _get_image_transforms(image_size)
    
    embeddings = []
    
    with torch.no_grad():
        for i in tqdm(range(0, len(image_paths), batch_size), desc="Extracting embeddings"):
            batch_paths = image_paths[i:i + batch_size]
            batch_tensors = []
            
            for path in batch_paths:
                try:
                    img = Image.open(path).convert("RGB")
                    tensor = transform(img)  # (3, H, W)
                    batch_tensors.append(tensor)
                except Exception as e:
                    logger.warning(f"Failed to load {path}: {e}")
                    # Use zero embedding for failed images
                    batch_tensors.append(torch.zeros(3, image_size, image_size))
            
            batch = torch.stack(batch_tensors)  # (B, 3, H, W)
            feats = model(batch)                # (B, 2048, 1, 1)
            feats = feats.squeeze(-1).squeeze(-1)  # (B, 2048)
            embeddings.append(feats.numpy())
    
    return np.vstack(embeddings)  # (N, 2048)


def run_vision_extraction(
    images_df: pd.DataFrame,
    config: dict,
    force_recompute: bool = False,
) -> pd.DataFrame:
    """Run complete vision feature extraction pipeline.
    
    This is the main entry point for the vision stage. It:
    1. Checks for cached results
    2. Extracts handcrafted features from all images
    3. Extracts ResNet50 deep embeddings
    4. Reduces embeddings via PCA to configured n_components
    5. Saves results to parquet cache
    
    Parameters
    ----------
    images_df : pd.DataFrame
        From loader.list_creative_images()
    config : dict
        Pipeline configuration dictionary
    force_recompute : bool
        If True, ignore cache and recompute
        
    Returns
    -------
    pd.DataFrame
        One row per image with all visual features + PCA-reduced embeddings.
        Key columns: filename, slug, request_id, placement_type, + visual features
    """
    cfg = config["vision"]
    cache_path = Path(cfg["cache_path"])
    
    # Check cache
    if cache_path.exists() and not force_recompute:
        logger.info(f"Loading vision features from cache: {cache_path}")
        return pd.read_parquet(cache_path)
    
    logger.info(f"Starting vision feature extraction for {len(images_df)} images...")
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    
    # --- Step 1: Handcrafted features ---
    logger.info("Extracting handcrafted visual features...")
    handcrafted_records = []
    for _, row in tqdm(images_df.iterrows(), total=len(images_df), desc="Handcrafted features"):
        try:
            img = Image.open(row["filepath"]).convert("RGB")
            feats = extract_handcrafted_features(img)
            feats["file_size_kb"] = row["file_size_kb"]
            handcrafted_records.append(feats)
        except Exception as e:
            logger.warning(f"Handcrafted extraction failed for {row['filepath']}: {e}")
            handcrafted_records.append({
                "aspect_ratio": 1.0, "image_width": 0.0, "image_height": 0.0,
                "brightness_mean": 0.5, "saturation_mean": 0.0, "colorfulness": 0.0,
                "visual_entropy": 0.0, "color_diversity_score": 0.0,
                "is_dark_background": 0.0, "is_light_background": 0.0,
            })
    
    handcrafted_df = pd.DataFrame(handcrafted_records)
    
    # --- Step 2: Deep embeddings ---
    torch_available = True
    try:
        image_paths = images_df["filepath"].tolist()
        embeddings = extract_deep_embeddings(
            image_paths,
            batch_size=cfg.get("batch_size", 16),
            image_size=cfg.get("image_size", 224),
        )
        logger.info(f"Raw embeddings shape: {embeddings.shape}")
    except ImportError:
        logger.warning(
            "PyTorch not available. Falling back to zero embeddings. "
            "Install torch: pip install torch torchvision"
        )
        embeddings = np.zeros((len(images_df), 2048))
        torch_available = False
    
    # --- Step 3: PCA dimensionality reduction ---
    n_components = cfg.get("pca_components", 32)

    if not torch_available:
        # Skip PCA when torch is absent: embeddings are all-zero, PCA would produce NaN.
        # Emit zero PCA columns so the schema is consistent for downstream models.
        logger.warning(
            "Skipping PCA: zero embeddings from missing PyTorch. "
            "vision_pca_* columns will be all zeros. "
            "Install torch for meaningful deep embeddings."
        )
        pca_cols = [f"vision_pca_{i}" for i in range(n_components)]
        pca_df = pd.DataFrame(
            np.zeros((len(images_df), n_components), dtype=np.float32),
            columns=pca_cols,
        )
        # Save a null PCA placeholder so inference code doesn't crash
        pca_model_path = cache_path.parent / "pca_model.pkl"
        with open(pca_model_path, "wb") as f:
            pickle.dump({"scaler": None, "pca": None, "torch_available": False}, f)
    else:
        logger.info(f"Reducing embeddings from 2048 to {n_components} dims via PCA...")
        from sklearn.decomposition import PCA
        from sklearn.preprocessing import StandardScaler

        scaler = StandardScaler()
        embeddings_scaled = scaler.fit_transform(embeddings)

        pca = PCA(n_components=min(n_components, embeddings.shape[0] - 1), random_state=42)
        embeddings_pca = pca.fit_transform(embeddings_scaled)

        explained_var = pca.explained_variance_ratio_.sum()
        logger.info(f"PCA: {n_components} components explain {explained_var:.1%} of variance")

        # Save PCA model for inference reuse
        pca_model_path = cache_path.parent / "pca_model.pkl"
        with open(pca_model_path, "wb") as f:
            pickle.dump({"scaler": scaler, "pca": pca, "torch_available": True}, f)
        logger.info(f"PCA model saved to {pca_model_path}")

        pca_cols = [f"vision_pca_{i}" for i in range(embeddings_pca.shape[1])]
        pca_df = pd.DataFrame(embeddings_pca, columns=pca_cols)

    # --- Combine all features ---
    # IMPORTANT: images_df already has file_size_kb; handcrafted_df must NOT include it.
    # Drop file_size_kb from handcrafted_df to prevent duplicate column error.
    handcrafted_df = handcrafted_df.drop(columns=["file_size_kb"], errors="ignore")

    result_df = pd.concat([
        images_df[["filename", "slug", "request_id", "placement_type", "file_size_kb"]].reset_index(drop=True),
        handcrafted_df.reset_index(drop=True),
        pca_df.reset_index(drop=True),
    ], axis=1)

    # Final guard: ensure no duplicate columns
    if result_df.columns.duplicated().any():
        dupes = result_df.columns[result_df.columns.duplicated()].tolist()
        logger.warning(f"Dropping duplicate columns: {dupes}")
        result_df = result_df.loc[:, ~result_df.columns.duplicated()]

    # Save to cache
    result_df.to_parquet(cache_path, index=False)
    logger.info(f"Vision features saved to {cache_path} ({len(result_df)} rows, {result_df.shape[1]} columns)")
    
    return result_df
