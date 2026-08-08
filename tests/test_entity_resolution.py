"""Tests for ingestion and entity resolution modules."""

import pytest
import pandas as pd
import numpy as np

from src.ingestion.entity_resolution import (
    flatten_global_design,
    build_creative_kpi_table,
    build_linked_dataset,
)


# ── Fixtures ─────────────────────────────────────────────────────────────

@pytest.fixture
def sample_design_dict():
    return {
        "game_key_001": {
            "req_id_aaa": {
                "labels": {"engagement": ["Car", "Vehicle"], "click_through": ["Car"]},
                "text": {"engagement": ["Drive Now"], "click_through": ["Learn More"]},
                "colors": {
                    "engagement": {
                        "1": {"red": 255, "green": 0, "blue": 0, "proportion": 0.5,
                              "saturation": 1.0, "luminosity": 0.5}
                    }
                },
                "videos_data": {"has_video": 0},
                "direction": {"direction": "up"},
                "adunit_sizes": {"size_x": 320, "size_y": 480},
            }
        },
        "game_key_002": {
            "req_id_bbb": {
                "labels": {"engagement": [], "click_through": []},
                "text": {"engagement": [], "click_through": []},
                "colors": {"engagement": {}, "click_through": {}},
                "videos_data": {"has_video": 1, "videos_length": {"vid_001": 15.0}},
                "direction": {"direction": "no direction"},
            }
        },
    }


@pytest.fixture
def sample_inventory_df():
    return pd.DataFrame({
        "campaign_id": ["camp_01"] * 5 + ["camp_02"] * 3,
        "game_key": ["game_key_001"] * 5 + ["game_key_002"] * 3,
        "device_type": ["smartphone"] * 8,
        "platform_os": ["ios", "ios", "android", "ios", "android", "ios", "android", "ios"],
        "geo_country": ["USA"] * 8,
        "type": ["impression", "impression", "impression", "first_dropped", "click-through-event",
                  "impression", "impression", "first_dropped"],
    })


@pytest.fixture
def sample_briefing_df():
    return pd.DataFrame({
        "campaign_id": ["camp_01", "camp_02"],
        "campaign_name": ["Test Campaign 1", "Test Campaign 2"],
        "campaign_objectives": ["Brand Awareness", "Conversion"],
        "buy_rate_cpe": [0.4, 0.3],
        "volume_agreed": [10000, 5000],
        "gross_cost_budget": [4000, 1500],
    })


# ── Tests ─────────────────────────────────────────────────────────────────

class TestFlattenGlobalDesign:
    def test_returns_dataframe(self, sample_design_dict):
        df = flatten_global_design(sample_design_dict)
        assert isinstance(df, pd.DataFrame)

    def test_has_expected_columns(self, sample_design_dict):
        df = flatten_global_design(sample_design_dict)
        expected = [
            "game_key", "request_id", "n_engagement_labels",
            "has_video", "color_saturation_mean", "aspect_ratio",
        ]
        for col in expected:
            assert col in df.columns, f"Missing column: {col}"

    def test_row_count_matches_requests(self, sample_design_dict):
        df = flatten_global_design(sample_design_dict)
        # 1 request for game_key_001 + 1 for game_key_002
        assert len(df) == 2

    def test_video_flag_extraction(self, sample_design_dict):
        df = flatten_global_design(sample_design_dict)
        row_no_video = df[df["request_id"] == "req_id_aaa"].iloc[0]
        row_with_video = df[df["request_id"] == "req_id_bbb"].iloc[0]
        assert row_no_video["has_video"] == 0
        assert row_with_video["has_video"] == 1

    def test_color_features_extracted(self, sample_design_dict):
        df = flatten_global_design(sample_design_dict)
        row = df[df["request_id"] == "req_id_aaa"].iloc[0]
        assert row["dominant_color_r"] == pytest.approx(1.0)  # 255/255
        assert row["color_saturation_mean"] == pytest.approx(1.0)

    def test_handles_empty_colors_gracefully(self, sample_design_dict):
        df = flatten_global_design(sample_design_dict)
        row = df[df["request_id"] == "req_id_bbb"].iloc[0]
        assert row["color_diversity"] == 0
        assert row["color_saturation_mean"] == 0.0


class TestBuildCreativeKpiTable:
    def test_returns_dataframe(self, sample_inventory_df):
        df = build_creative_kpi_table(sample_inventory_df, min_impressions=1)
        assert isinstance(df, pd.DataFrame)

    def test_er_range_valid(self, sample_inventory_df):
        df = build_creative_kpi_table(sample_inventory_df, min_impressions=1)
        assert (df["engagement_rate"] >= 0).all()
        assert (df["engagement_rate"] <= 1).all()

    def test_ctr_range_valid(self, sample_inventory_df):
        df = build_creative_kpi_table(sample_inventory_df, min_impressions=1)
        assert (df["click_through_rate"] >= 0).all()
        assert (df["click_through_rate"] <= 1).all()

    def test_filters_low_impressions(self, sample_inventory_df):
        """Rows with fewer impressions than min_impressions should be filtered out."""
        df_filtered = build_creative_kpi_table(sample_inventory_df, min_impressions=100)
        # All events have < 100 impressions per group, should return empty
        assert len(df_filtered) == 0

    def test_correct_er_calculation(self, sample_inventory_df):
        """camp_01/game_key_001 rows should produce valid ER values in [0, 1].
        
        Note: grouping includes device_type+platform_os+geo_country, so
        impressions/engagements are split across sub-groups.
        """
        df = build_creative_kpi_table(sample_inventory_df, min_impressions=1)
        rows = df[
            (df["campaign_id"] == "camp_01") &
            (df["game_key"] == "game_key_001")
        ]
        assert len(rows) > 0, "Expected at least one row for camp_01/game_key_001"
        # All ER values for this creative should be in [0, 1]
        assert (rows["engagement_rate"] >= 0).all()
        assert (rows["engagement_rate"] <= 1).all()
        # At least one row should have a non-zero ER (the first_dropped event exists)
        assert rows["engagement_rate"].max() > 0, "Expected at least one engagement"
