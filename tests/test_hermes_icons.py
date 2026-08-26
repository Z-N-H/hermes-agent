"""Tests for hermes_icons.NerdFontIcons lookup + back-compat constants."""

from __future__ import annotations

import json

import pytest

import hermes_icons
from hermes_icons import (
    ICON_BAN,
    ICON_BOLT,
    ICON_BOX,
    ICON_BRAND,
    ICON_CHART,
    ICON_CHEVRON_RIGHT,
    ICON_COMMENT,
    ICON_COMPRESS,
    ICON_DICE,
    ICON_EYE,
    ICON_FAIL,
    ICON_FAIL_CIRCLE,
    ICON_FLOPPY,
    ICON_FOLDER,
    ICON_GEAR,
    ICON_GLOBE,
    ICON_LIST,
    ICON_MAGNIFY,
    ICON_NAMES,
    ICON_NOTE,
    ICON_OK,
    ICON_OK_CIRCLE,
    ICON_PHONE,
    ICON_PROMPT,
    ICON_ROBOT,
    ICON_ROCKET,
    ICON_ROTATE,
    ICON_WARN,
    ICON_WRENCH,
    NerdFontIcons,
)

# (constant_name, nerd-font key) — each back-compat alias must be wired to the
# key that produces its canonical codepoint. This is the load-bearing
# relationship test: it proves the alias points at the right glyph without
# freezing a catalog snapshot.
BACKCOMPAT_ALIASES: list[tuple[str, str]] = [
    ("ICON_BRAND", "fa-feather"),
    ("ICON_PROMPT", "fa-chevron_right"),
    ("ICON_CHEVRON_RIGHT", "fa-chevron_right"),
    ("ICON_OK", "fa-check"),
    ("ICON_OK_CIRCLE", "fa-circle_check"),
    ("ICON_FAIL", "fa-xmark"),
    ("ICON_FAIL_CIRCLE", "fa-circle_xmark"),
    ("ICON_WARN", "fa-triangle_exclamation"),
    ("ICON_BAN", "fa-ban"),
    ("ICON_BOLT", "fa-bolt"),
    ("ICON_GEAR", "fa-gear"),
    ("ICON_COMPRESS", "fa-compress"),
    ("ICON_ROTATE", "fa-arrows_rotate"),
    ("ICON_EYE", "fa-eye"),
    ("ICON_MAGNIFY", "fa-magnifying_glass"),
    ("ICON_FLOPPY", "fa-floppy_disk"),
    ("ICON_PHONE", "fa-phone"),
    ("ICON_COMMENT", "fa-comment"),
    ("ICON_ROBOT", "md-robot"),
    ("ICON_WRENCH", "fa-screwdriver_wrench"),
    ("ICON_GLOBE", "fa-globe"),
    ("ICON_ROCKET", "fa-rocket"),
    ("ICON_CHART", "fa-chart_bar"),
    ("ICON_LIST", "fa-clipboard_list"),
    ("ICON_NOTE", "fa-note_sticky"),
    ("ICON_BOX", "fa-box"),
    ("ICON_FOLDER", "fa-folder"),
    ("ICON_DICE", "fa-dice"),
]

# Stable, documented Nerd Font v3 PUA assignments — behavior contracts, not
# catalog snapshots. These FontAwesome codepoints are locked across releases.
STABLE_CODEPOINTS: dict[str, str] = {
    "ICON_OK": "\uf00c",
    "ICON_WARN": "\uf071",
    "ICON_FAIL": "\uf00d",
    "ICON_ROBOT": "\U000f06a9",
}


class TestGet:
    """Tests for NerdFontIcons.get() — forward key -> character lookup."""

    def test_known_key_returns_expected_codepoint(self):
        """get('fa-check') returns the canonical check-mark codepoint."""
        assert NerdFontIcons.get("fa-check") == "\uf00c"

    def test_returns_single_character_string(self):
        """Every lookup yields a non-empty string."""
        ch = NerdFontIcons.get("md-robot")
        assert isinstance(ch, str)
        assert len(ch) >= 1

    def test_missing_key_returns_empty_default(self):
        assert NerdFontIcons.get("does-not-exist") == ""

    def test_missing_key_returns_custom_default(self):
        assert NerdFontIcons.get("does-not-exist", "fallback") == "fallback"

    def test_md_prefix_lookup_works(self):
        """Material Design icons resolve through the 'md-' prefix."""
        assert NerdFontIcons.get("md-robot") == "\U000f06a9"


class TestKeys:
    """Tests for NerdFontIcons.keys() — catalog enumeration."""

    def test_excludes_metadata_block(self):
        """The upstream METADATA entry is not an icon and must be excluded."""
        assert "METADATA" not in NerdFontIcons.keys()

    def test_returns_large_nonempty_catalog(self):
        """Invariant: the catalog is large (floor, not an exact count)."""
        ks = NerdFontIcons.keys()
        assert len(ks) > 1000
        assert all(isinstance(k, str) for k in ks)

    def test_keys_match_cache_length(self):
        """keys() length equals the cached entry count."""
        NerdFontIcons.get("fa-check")
        assert NerdFontIcons._cache is not None
        assert len(NerdFontIcons.keys()) == len(NerdFontIcons._cache)


class TestFind:
    """Tests for NerdFontIcons.find() — fuzzy substring search."""

    def test_substring_matches_known_glyphs(self):
        """find('check') surfaces both fa-check and fa-circle_check."""
        results = NerdFontIcons.find("check")
        assert "fa-check" in results
        assert "fa-circle_check" in results

    def test_all_results_contain_query(self):
        """Invariant: every result contains the query as a substring."""
        q = "robot"
        results = NerdFontIcons.find(q)
        assert all(q in r.lower() for r in results)
        assert "md-robot" in results

    def test_case_insensitive(self):
        """Search is case-insensitive."""
        assert "fa-check" in NerdFontIcons.find("CHECK")

    def test_empty_query_matches_everything(self):
        """An empty query is a substring of all keys."""
        assert len(NerdFontIcons.find("")) == len(NerdFontIcons.keys())

    def test_no_match_returns_empty_list(self):
        assert NerdFontIcons.find("zzz-not-a-real-glyph") == []


class TestLazyLoad:
    """Tests for the lazy, cached JSON parse."""

    def test_cache_populated_after_first_access(self):
        """The first lookup triggers a load and populates the cache."""
        NerdFontIcons._reset()
        assert NerdFontIcons._cache is None
        NerdFontIcons.get("fa-check")
        assert NerdFontIcons._cache is not None
        assert NerdFontIcons._by_emoji is not None

    def test_reset_clears_cache(self):
        """_reset() returns the class to the unloaded state."""
        NerdFontIcons.get("fa-check")
        NerdFontIcons._reset()
        assert NerdFontIcons._cache is None
        assert NerdFontIcons._by_emoji is None

    def test_load_is_idempotent(self):
        """Re-loading does not change any resolved value."""
        before = NerdFontIcons.get("fa-check")
        NerdFontIcons._load()
        after = NerdFontIcons.get("fa-check")
        assert before == after

    def test_reload_after_reset(self):
        """A fresh load after reset reproduces the same values."""
        first = NerdFontIcons.get("md-robot")
        NerdFontIcons._reset()
        second = NerdFontIcons.get("md-robot")
        assert first == second == "\U000f06a9"

    def test_json_file_exists_at_expected_path(self):
        """The data file is committed alongside the module."""
        assert NerdFontIcons._json_path.is_file()

    def test_metadata_version_present(self):
        """Invariant: upstream METADATA block carries a non-empty version."""
        data = json.loads(NerdFontIcons._json_path.read_text(encoding="utf-8"))
        meta = data["METADATA"]
        assert isinstance(meta["version"], str) and meta["version"]


class TestBackCompatConstants:
    """Tests that ICON_* aliases are wired to the correct nerd-font keys."""

    @pytest.mark.parametrize("name,key", BACKCOMPAT_ALIASES)
    def test_alias_matches_lookup(self, name, key):
        """Each constant equals NerdFontIcons.get(<its key>) and is non-empty."""
        val = getattr(hermes_icons, name)
        assert val == NerdFontIcons.get(key)
        assert val

    @pytest.mark.parametrize("name,expected", STABLE_CODEPOINTS.items())
    def test_stable_codepoints(self, name, expected):
        """A few well-known codepoints are locked behavior contracts."""
        assert getattr(hermes_icons, name) == expected

    def test_chevron_alias_shares_prompt_value(self):
        """ICON_CHEVRON_RIGHT is an alias of ICON_PROMPT (same glyph)."""
        assert ICON_CHEVRON_RIGHT == ICON_PROMPT

    def test_all_alias_values_present_in_icon_names(self):
        """Every back-compat constant's value appears in ICON_NAMES.values()."""
        values = set(ICON_NAMES.values())
        for name, _ in BACKCOMPAT_ALIASES:
            assert getattr(hermes_icons, name) in values

    def test_icon_names_spot_check(self):
        """A few ICON_NAMES entries map back to their constants."""
        assert ICON_NAMES["ok"] == ICON_OK
        assert ICON_NAMES["warn"] == ICON_WARN
        assert ICON_NAMES["robot"] == ICON_ROBOT
        assert ICON_NAMES["brand"] == ICON_BRAND

    def test_icon_names_all_values_nonempty(self):
        """Invariant: no ICON_NAMES entry resolves to an empty string."""
        assert all(v for v in ICON_NAMES.values())


class TestGetByEmoji:
    """Tests for NerdFontIcons.get_by_emoji() — emoji -> Nerd Font replacement."""

    def test_rocket_emoji_resolves(self):
        """🚀 maps to the fa-rocket glyph."""
        assert NerdFontIcons.get_by_emoji("\U0001f680") == NerdFontIcons.get("fa-rocket")

    def test_check_emoji_resolves(self):
        """✅ maps to the fa-circle_check glyph."""
        assert NerdFontIcons.get_by_emoji("\u2705") == NerdFontIcons.get("fa-circle_check")

    def test_robot_emoji_resolves(self):
        """🤖 maps to the md-robot glyph."""
        assert NerdFontIcons.get_by_emoji("\U0001f916") == NerdFontIcons.get("md-robot")

    def test_warn_emoji_with_variation_selector(self):
        """⚠️ (with VS16) resolves to the warning glyph."""
        assert NerdFontIcons.get_by_emoji("\u26a0\ufe0f") == NerdFontIcons.get(
            "fa-triangle_exclamation"
        )

    def test_unknown_emoji_returns_default(self):
        assert NerdFontIcons.get_by_emoji("\U0001f389") == ""  # 🎉 — not curated
        assert NerdFontIcons.get_by_emoji("\U0001f389", "fallback") == "fallback"

    def test_resolved_value_is_nonempty(self):
        """Every curated emoji resolves to a non-empty replacement."""
        for emoji in NerdFontIcons._EMOJI_TO_KEY:
            assert NerdFontIcons.get_by_emoji(emoji)
