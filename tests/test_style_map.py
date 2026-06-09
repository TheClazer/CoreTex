"""Tests for the configurable Word-style → IR-role mapping."""

from __future__ import annotations

import json

from app.converter.style_map import StyleMap, load_style_map


def test_heading_mapping_is_case_insensitive_and_clamped():
    sm = StyleMap(headings={"Chapter Title": 1, "Deep": 9})
    assert sm.heading_level("chapter title") == 1
    assert sm.heading_level("  CHAPTER TITLE  ") == 1
    assert sm.heading_level("Deep") == 4  # clamped to max level 4
    assert sm.heading_level("Unknown") is None
    assert sm.heading_level(None) is None


def test_code_membership():
    sm = StyleMap(code=["Code", "Source Code"])
    assert sm.is_code("code") is True
    assert sm.is_code("Source Code") is True
    assert sm.is_code("Normal") is False


def test_list_kind():
    sm = StyleMap(lists={"House Bullets": "bullet", "House Numbers": "Number"})
    assert sm.list_kind("house bullets") == "bullet"
    assert sm.list_kind("House Numbers") == "number"
    assert sm.list_kind("Body") is None


def test_empty_map_is_inert():
    sm = StyleMap()
    assert sm.is_empty
    assert sm.heading_level("Chapter Title") is None
    assert sm.is_code("Code") is False
    assert sm.list_kind("House Bullets") is None


def test_load_from_file(tmp_path):
    cfg = tmp_path / "style_map.json"
    cfg.write_text(
        json.dumps({"headings": {"Chapter Title": 2}, "code": ["Listing"]}),
        encoding="utf-8",
    )
    sm = load_style_map(str(cfg))
    assert sm.heading_level("Chapter Title") == 2
    assert sm.is_code("Listing") is True


def test_load_missing_file_returns_empty(tmp_path):
    sm = load_style_map(str(tmp_path / "nope.json"))
    assert sm.is_empty


def test_load_invalid_json_returns_empty(tmp_path):
    cfg = tmp_path / "broken.json"
    cfg.write_text("{ not valid json", encoding="utf-8")
    sm = load_style_map(str(cfg))
    assert sm.is_empty
