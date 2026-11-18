"""Small reusable widgets shared by the pages.

Every widget is dumb: it takes already-computed values and paints them. No
widget collects data, starts work or builds SQL, so the pages stay the only
place that knows how the widgets fit together.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QLabel,
    QProgressBar,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


class Card(QFrame):
    """A titled container with a large value and an optional hint line."""

    def __init__(
        self,
        title: str,
        value: str = "—",
        hint: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        self.setFrameShape(QFrame.Shape.StyledPanel)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(4)

        self._title = QLabel(title, self)
        self._title.setObjectName("CardTitle")
        layout.addWidget(self._title)

        self._value = QLabel(value, self)
        self._value.setObjectName("CardValue")
        self._value.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        layout.addWidget(self._value)

        self._hint = QLabel(hint, self)
        self._hint.setObjectName("CardHint")
        self._hint.setWordWrap(True)
        self._hint.setVisible(bool(hint))
        layout.addWidget(self._hint)

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

    def set_value(self, value: str) -> None:
        """Replace the big value line."""
        self._value.setText(value)

    def set_hint(self, hint: str) -> None:
        """Replace the hint line and hide it when there is nothing to say."""
        self._hint.setText(hint)
        self._hint.setVisible(bool(hint))


class MetricBar(QWidget):
    """A labelled percentage bar.

    ``value`` is ``None`` when the metric is unknown, which draws an empty track
    and the literal ``—`` instead of a fabricated ``0%``.
    """

    def __init__(self, label: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        header = QGridLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setHorizontalSpacing(8)

        self._label = QLabel(label, self)
        self._label.setObjectName("FieldLabel")
        header.addWidget(self._label, 0, 0)

        self._value = QLabel("—", self)
        self._value.setObjectName("FieldValue")
        self._value.setAlignment(Qt.AlignmentFlag.AlignRight)
        header.addWidget(self._value, 0, 1)

        layout.addLayout(header)

        self._bar = QProgressBar(self)
        self._bar.setObjectName("MetricBar")
        self._bar.setRange(0, 100)
        self._bar.setTextVisible(False)
        self._bar.setFixedHeight(8)
        layout.addWidget(self._bar)

    def set_value(self, percent: float | None, text: str | None = None) -> None:
        """Show ``percent`` (0-100) or an unknown marker when it is ``None``."""
        if percent is None:
            self._bar.setValue(0)
            self._value.setText("—")
            return
        clamped = max(0.0, min(100.0, float(percent)))
        self._bar.setValue(int(round(clamped)))
        self._value.setText(text if text is not None else f"{clamped:.0f}%")


class FieldRow(QWidget):
    """A ``label: value`` line used by the detail sections."""

    def __init__(self, label: str, value: str = "—", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QGridLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)
        layout.setHorizontalSpacing(12)
        layout.setColumnStretch(1, 1)

        self._label = QLabel(label, self)
        self._label.setObjectName("FieldLabel")
        layout.addWidget(self._label, 0, 0, Qt.AlignmentFlag.AlignTop)

        self._value = QLabel(value, self)
        self._value.setObjectName("FieldValue")
        self._value.setWordWrap(True)
        self._value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self._value, 0, 1)

    def set_value(self, value: str) -> None:
        """Replace the value text; an empty string shows ``—``."""
        self._value.setText(value or "—")


def section_title(text: str, parent: QWidget | None = None) -> QLabel:
    """Return a section heading label."""
    label = QLabel(text, parent)
    label.setObjectName("SectionTitle")
    return label


def notice(text: str, parent: QWidget | None = None) -> QLabel:
    """Return the limitation notice label.

    The caller decides whether to show it; an empty string produces a hidden
    label so a page can build its layout once.
    """
    label = QLabel(text, parent)
    label.setObjectName("Notice")
    label.setWordWrap(True)
    label.setVisible(bool(text))
    return label


def as_text(value: Any, *, unit: str = "", missing: str = "—") -> str:
    """Format a value for display, or return ``missing`` when it is unknown.

    Formatting lives here so no page invents a placeholder of its own and every
    unknown field reads the same way.
    """
    if value is None or value == "":
        return missing
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, float):
        return f"{value}{unit}"
    if isinstance(value, int):
        return f"{value}{unit}"
    return f"{value}{unit}"