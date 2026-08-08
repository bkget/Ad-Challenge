"""Tests for vision feature extraction module."""

import numpy as np
import pytest
from PIL import Image

from src.vision.extractor import extract_handcrafted_features


@pytest.fixture
def red_image():
    """Solid red 224x224 image."""
    img = Image.new("RGB", (224, 224), color=(255, 0, 0))
    return img


@pytest.fixture
def dark_image():
    """Very dark image."""
    img = Image.new("RGB", (224, 224), color=(10, 10, 10))
    return img


@pytest.fixture
def white_image():
    """All-white image."""
    img = Image.new("RGB", (224, 224), color=(255, 255, 255))
    return img


@pytest.fixture
def tall_image():
    """Portrait image (320x480)."""
    img = Image.new("RGB", (320, 480), color=(128, 128, 128))
    return img


class TestExtractHandcraftedFeatures:
    def test_returns_dict(self, red_image):
        feats = extract_handcrafted_features(red_image)
        assert isinstance(feats, dict)

    def test_has_required_keys(self, red_image):
        feats = extract_handcrafted_features(red_image)
        required = [
            "aspect_ratio", "brightness_mean", "saturation_mean",
            "colorfulness", "visual_entropy", "color_diversity_score",
            "is_dark_background", "is_light_background",
        ]
        for key in required:
            assert key in feats, f"Missing key: {key}"

    def test_aspect_ratio_square(self, red_image):
        feats = extract_handcrafted_features(red_image)
        assert feats["aspect_ratio"] == pytest.approx(1.0)

    def test_aspect_ratio_portrait(self, tall_image):
        feats = extract_handcrafted_features(tall_image)
        expected = 320 / 480
        assert feats["aspect_ratio"] == pytest.approx(expected, rel=0.01)

    def test_dark_background_flag(self, dark_image):
        feats = extract_handcrafted_features(dark_image)
        assert feats["is_dark_background"] == 1.0
        assert feats["is_light_background"] == 0.0

    def test_light_background_flag(self, white_image):
        feats = extract_handcrafted_features(white_image)
        assert feats["is_light_background"] == 1.0
        assert feats["is_dark_background"] == 0.0

    def test_brightness_range(self, red_image):
        feats = extract_handcrafted_features(red_image)
        assert 0.0 <= feats["brightness_mean"] <= 1.0

    def test_saturation_range(self, red_image):
        feats = extract_handcrafted_features(red_image)
        assert 0.0 <= feats["saturation_mean"] <= 1.0

    def test_entropy_non_negative(self, red_image):
        feats = extract_handcrafted_features(red_image)
        # Near-zero entropy expected for solid-color; allow tiny float epsilon
        assert feats["visual_entropy"] >= -1e-6

    def test_all_values_are_floats(self, red_image):
        feats = extract_handcrafted_features(red_image)
        for k, v in feats.items():
            assert isinstance(v, float), f"Feature '{k}' is {type(v)}, expected float"
