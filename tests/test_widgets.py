"""Widgets render values without collecting anything."""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QLabel  # noqa: E402


def _label(widget: object, object_name: str) -> QLabel:
    from PySide6.QtWidgets import QLabel as Label

    found = widget.findChild(Label, object_name)
    assert found is not None, f"missing child {object_name!r}"
    return found


def test_card_shows_value_and_hint(qt_app) -> None:
    from pcinsight.ui import widgets

    card = widgets.Card("CPU load", "12%", "4 physical / 8 logical")

    assert _label(card, "CardValue").text() == "12%"
    assert "4 physical" in _label(card, "CardHint").text()


def test_card_hint_hides_when_empty(qt_app) -> None:
    from pcinsight.ui import widgets

    card = widgets.Card("Memory")

    assert _label(card, "CardValue").text() == "—"
    assert not _label(card, "CardHint").isVisibleTo(card)


def test_card_hint_can_be_replaced(qt_app) -> None:
    from pcinsight.ui import widgets

    card = widgets.Card("Memory", "40%", "old hint")
    card.set_hint("new hint")

    assert _label(card, "CardHint").text() == "new hint"


def test_metric_bar_clamps_and_formats(qt_app) -> None:
    from pcinsight.ui import widgets

    bar = widgets.MetricBar("Used")
    bar.set_value(140.0)

    assert bar._bar.value() == 100
    assert bar._value.text() == "100%"


def test_metric_bar_shows_unknown_without_faking_zero(qt_app) -> None:
    from pcinsight.ui import widgets

    bar = widgets.MetricBar("Used")
    bar.set_value(None)

    assert bar._bar.value() == 0
    assert bar._value.text() == "—"


def test_metric_bar_uses_a_custom_text(qt_app) -> None:
    from pcinsight.ui import widgets

    bar = widgets.MetricBar("Used")
    bar.set_value(40.0, text="40% used")

    assert bar._value.text() == "40% used"


def test_field_row_replaces_values(qt_app) -> None:
    from pcinsight.ui import widgets

    row = widgets.FieldRow("Processor", "old")
    row.set_value("new")

    assert row._value.text() == "new"

    row.set_value("")

    assert row._value.text() == "—"


def test_notice_hides_itself_without_text(qt_app) -> None:
    from pcinsight.ui import widgets

    empty = widgets.notice("")
    filled = widgets.notice("Limited mode")

    assert not empty.isVisibleTo(empty)
    assert filled.isVisibleTo(filled)


def test_as_text_formats_values_and_missing(qt_app) -> None:
    from pcinsight.ui import widgets

    assert widgets.as_text(12.5, unit="%") == "12.5%"
    assert widgets.as_text(4) == "4"
    assert widgets.as_text(True) == "yes"
    assert widgets.as_text(None) == "—"
    assert widgets.as_text("") == "—"