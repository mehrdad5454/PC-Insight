"""Theme resolution and the generated stylesheet."""

from __future__ import annotations

from pcinsight.ui import theme


def test_theme_keys_are_concrete() -> None:
    assert theme.theme_key("light") == "light"
    assert theme.theme_key("dark") == "dark"
    assert theme.theme_key("system", is_dark=True) == "dark"
    assert theme.theme_key("system", is_dark=False) == "light"


def test_theme_key_falls_back_for_unknown_names() -> None:
    assert theme.theme_key("neon") == "light"
    assert theme.theme_key("") == "light"


def test_resolve_theme_exposes_every_token_used_by_the_stylesheet() -> None:
    for key in ("light", "dark"):
        colors = theme.resolve_theme(key)
        assert set(colors) >= {
            "background",
            "surface",
            "border",
            "text",
            "accent",
            "notice_background",
            "track",
        }


def test_style_sheet_is_formatted_for_both_themes() -> None:
    for key in ("light", "dark"):
        sheet = theme.style_sheet(key)
        assert "QWidget" in sheet
        assert "#" in sheet


def test_style_sheet_prefers_the_system_theme_when_asked() -> None:
    assert theme.style_sheet("system", is_dark=True) == theme.style_sheet("dark")
    assert theme.style_sheet("system", is_dark=False) == theme.style_sheet("light")


def test_light_and_dark_differ() -> None:
    assert theme.style_sheet("light") != theme.style_sheet("dark")