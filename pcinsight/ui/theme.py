"""Theme resolution and the single application stylesheet.

The theme is data only: one dict of colour tokens and one generated QSS string.
Widgets read their colours from :func:`style_sheet`; they never hard-code a
colour, so light and dark stay consistent from one place.

``system`` follows the desktop appearance reported by Qt, so P4 needs no
platform-specific registry or settings API.
"""

from __future__ import annotations

import logging

from ..config import DEFAULT_THEME, THEMES

logger = logging.getLogger(__name__)

# Ordered by contrast: ``text`` is the primary foreground, ``text_muted`` and
# ``text_dim`` are progressively quieter, ``line`` is a border.
_COLORS: dict[str, dict[str, str]] = {
    "light": {
        "background": "#f4f5f7",
        "surface": "#ffffff",
        "surface_alt": "#fbfbfc",
        "border": "#dfe1e6",
        "text": "#1b1d21",
        "text_muted": "#5a5f68",
        "text_dim": "#858b95",
        "accent": "#2f6fd0",
        "accent_hover": "#275fae",
        "accent_text": "#ffffff",
        "ok": "#1f7a45",
        "warning": "#a86400",
        "critical": "#b3261e",
        "notice_background": "#fdf3e3",
        "notice_border": "#e8cf9f",
        "notice_text": "#6b4a12",
        "track": "#e6e8ec",
    },
    "dark": {
        "background": "#15171b",
        "surface": "#1e2126",
        "surface_alt": "#23262c",
        "border": "#333840",
        "text": "#eef0f3",
        "text_muted": "#a8aeb8",
        "text_dim": "#7d848e",
        "accent": "#4c8dff",
        "accent_hover": "#6ba0ff",
        "accent_text": "#0d1117",
        "ok": "#5ac47f",
        "warning": "#e0a54a",
        "critical": "#ff6b60",
        "notice_background": "#2a2416",
        "notice_border": "#5c4a24",
        "notice_text": "#e8d3a3",
        "track": "#2a2e35",
    },
}

_BASE_QSS = """
QWidget {{
    background-color: {background};
    color: {text};
    font-family: "Segoe UI";
}}
QMainWindow, QDialog {{
    background-color: {background};
}}
QLabel {{
    background: transparent;
}}
QScrollArea {{
    background-color: {background};
    border: none;
}}
QFrame#Card {{
    background-color: {surface};
    border: 1px solid {border};
    border-radius: 8px;
}}
QLabel#CardTitle {{
    color: {text_muted};
    font-size: 11px;
    font-weight: 600;
}}
QLabel#CardValue {{
    color: {text};
    font-size: 20px;
    font-weight: 600;
}}
QLabel#CardHint {{
    color: {text_dim};
    font-size: 11px;
}}
QLabel#SectionTitle {{
    color: {text};
    font-size: 15px;
    font-weight: 600;
}}
QLabel#PageTitle {{
    color: {text};
    font-size: 20px;
    font-weight: 600;
}}
QLabel#PageSubtitle {{
    color: {text_muted};
    font-size: 12px;
}}
QLabel#FieldLabel {{
    color: {text_muted};
    font-size: 11px;
}}
QLabel#FieldValue {{
    color: {text};
    font-size: 12px;
}}
QLabel#Notice {{
    background-color: {notice_background};
    border: 1px solid {notice_border};
    border-radius: 6px;
    color: {notice_text};
    padding: 6px 10px;
}}
QPushButton#NavButton {{
    background: transparent;
    border: none;
    border-radius: 6px;
    color: {text_muted};
    padding: 9px 12px;
    text-align: left;
}}
QPushButton#NavButton:hover {{
    background-color: {surface_alt};
    color: {text};
}}
QPushButton#NavButton:checked {{
    background-color: {surface};
    color: {text};
    font-weight: 600;
}}
QPushButton#Action {{
    background-color: {accent};
    border: none;
    border-radius: 6px;
    color: {accent_text};
    font-weight: 600;
    padding: 8px 16px;
}}
QPushButton#Action:hover {{
    background-color: {accent_hover};
}}
QPushButton#Action:disabled {{
    background-color: {track};
    color: {text_dim};
}}
QProgressBar {{
    background-color: {track};
    border: none;
    border-radius: 4px;
    max-height: 8px;
    text-align: center;
}}
QProgressBar::chunk {{
    background-color: {accent};
    border-radius: 4px;
}}
"""


def theme_key(name: str, *, is_dark: bool = False) -> str:
    """Return the concrete theme name (``light`` or ``dark``) to use.

    An unknown name falls back to the default theme with a warning instead of
    raising: a value that cannot be read out of the database must not stop the
    window from opening.
    """
    key = (name or DEFAULT_THEME).strip().lower()
    if key not in THEMES:
        logger.warning("unknown theme %r, using %r", name, DEFAULT_THEME)
        key = DEFAULT_THEME
    if key == "system":
        key = "dark" if is_dark else "light"
    return key


def resolve_theme(name: str, *, is_dark: bool = False) -> dict[str, str]:
    """Return the colour set to use for ``name``."""
    return _COLORS.get(theme_key(name, is_dark=is_dark), _COLORS["light"])


def style_sheet(name: str, *, is_dark: bool = False) -> str:
    """Return the QSS for the resolved theme."""
    return _BASE_QSS.format(**resolve_theme(name, is_dark=is_dark))