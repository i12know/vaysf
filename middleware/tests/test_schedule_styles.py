"""Tests for schedule_styles.py — central palette for Issue #131."""
from __future__ import annotations

from config import SPORT_TYPE
from schedule_styles import (
    CATEGORY_STYLES,
    SPORT_STYLES,
    category_prefix,
    category_style,
    format_compact_label,
    infer_category,
    sport_style,
    style_for_game,
)


def test_category_styles_complete():
    """All five categories from Issue #131 must be present with hex colors."""
    expected = {"M", "W", "X", "N", "N35+"}
    assert expected.issubset(CATEGORY_STYLES.keys())
    for cs in CATEGORY_STYLES.values():
        assert len(cs.text_color) == 6
        int(cs.text_color, 16)  # valid hex


def test_sport_styles_cover_all_known_events():
    """Every SPORT_TYPE value should appear in SPORT_STYLES."""
    missing = set(SPORT_TYPE.values()) - set(SPORT_STYLES.keys())
    assert not missing, f"sports without a style: {missing}"


def test_sport_style_fill_is_valid_hex():
    for style in SPORT_STYLES.values():
        assert len(style.fill_color) == 6
        int(style.fill_color, 16)
        assert style.abbrev  # non-empty


def test_unknown_event_falls_back_safely():
    style = sport_style("Underwater Basket Weaving")
    assert style.fill_color == "EBF1DE"
    assert style.abbrev == "??"


def test_infer_category_uses_sport_styles_default_for_known_events():
    # SPORT_STYLES default beats event-name parsing (per Issue #131:
    # Basketball "Men Team" defaults to N; BC "Mixed Team" defaults to N).
    assert infer_category(SPORT_TYPE["BASKETBALL"]) == "N"
    assert infer_category(SPORT_TYPE["BIBLE_CHALLENGE"]) == "N"
    assert infer_category(SPORT_TYPE["VOLLEYBALL_MEN"]) == "M"
    assert infer_category(SPORT_TYPE["VOLLEYBALL_WOMEN"]) == "W"
    assert infer_category(SPORT_TYPE["SOCCER"]) == "X"


def test_infer_category_unknown_event_uses_name_heuristic():
    assert infer_category("Frisbee - Men Open") == "M"
    assert infer_category("Frisbee - Women Open") == "W"
    assert infer_category("Frisbee - Mixed Open") == "X"
    assert infer_category("Quidditch") == "N"


def test_infer_category_defaults_per_issue_131():
    # Basketball is "Men Team" in SPORT_TYPE but Issue #131 says default N.
    # Inference picks M from "Men" — caller must supply override or use
    # SPORT_STYLES default explicitly to get N.  Sport_style does that:
    assert sport_style(SPORT_TYPE["BASKETBALL"]).default_category == "N"
    assert sport_style(SPORT_TYPE["BIBLE_CHALLENGE"]).default_category == "N"
    assert sport_style(SPORT_TYPE["PICKLEBALL_35"]).default_category == "N35+"


def test_infer_category_sport_format_wins_over_event_name():
    # Badminton event with "Women" sport_format → W even though event name is generic.
    assert infer_category(SPORT_TYPE["BADMINTON"], "Women") == "W"
    assert infer_category(SPORT_TYPE["BADMINTON"], "Mixed Doubles") == "X"


def test_style_for_game_explicit_category_wins():
    game = {"event": SPORT_TYPE["BASKETBALL"], "category": "M"}
    _, cat_style, code = style_for_game(game)
    assert code == "M"
    assert cat_style.text_color == CATEGORY_STYLES["M"].text_color


def test_style_for_game_invalid_category_falls_back_to_inference():
    game = {"event": SPORT_TYPE["VOLLEYBALL_WOMEN"], "category": "Z"}
    _, _, code = style_for_game(game)
    assert code == "W"


def test_category_prefix_for_pickleball_35_uses_default():
    assert category_prefix(SPORT_TYPE["PICKLEBALL_35"]) == "N35+"


def test_format_compact_label():
    assert format_compact_label(SPORT_TYPE["VOLLEYBALL_MEN"]) == "M VB"
    assert format_compact_label(SPORT_TYPE["VOLLEYBALL_WOMEN"]) == "W VB"
    assert format_compact_label(SPORT_TYPE["BIBLE_CHALLENGE"]) == "N BC"
    assert format_compact_label(SPORT_TYPE["PICKLEBALL_35"]) == "N35+ PB"
    assert format_compact_label(SPORT_TYPE["BADMINTON"], "Women") == "W BD"
    assert format_compact_label(SPORT_TYPE["TENNIS"], category="X") == "X TN"


def test_category_style_fallback_to_n():
    cs = category_style(None)
    assert cs.code == "N"
    cs = category_style("nonexistent")
    assert cs.code == "N"
