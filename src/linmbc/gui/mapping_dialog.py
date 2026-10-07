"""Dialog for one button's action: which button, which keys, how it runs, delay."""

from PySide6.QtCore import QEvent, QPoint, Qt, Signal, Slot
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QToolButton,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

from linmbc.i18n import tr
from linmbc.keycapture import ComboRecorder, evdev_from_scancode
from linmbc.keynames import format_keys, parse_keys
from linmbc.keys import code_of, name_of
from linmbc.profile import (
    DEFAULT_DELAY_MS,
    MAX_COUNT,
    MAX_DELAY_MS,
    MIN_TIMED_DELAY_MS,
    Action,
    Delay,
    Mode,
)

# Shown when no mouse is detected yet; otherwise the rows come from the mouse itself.
STANDARD_BUTTONS = [
    code_of(n) for n in ("BTN_LEFT", "BTN_RIGHT", "BTN_MIDDLE", "BTN_SIDE", "BTN_EXTRA")
]
MODES = [Mode.HOLD, Mode.ONCE, Mode.TOGGLE, Mode.REPEAT]


def button_label(code: int) -> str:
    return tr(f"button.{name_of(code)}")


class KeysEdit(QLineEdit):
    """Free-typed keys ("Ctrl+2"); while recording, the pressed keys are captured instead."""

    recorded = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setPlaceholderText(tr("dialog.keys_placeholder"))
        self._recorder: ComboRecorder | None = None

    def start_recording(self) -> None:
        self._recorder = ComboRecorder()
        self.clear()
        self.setPlaceholderText(tr("dialog.recording"))
        self.setFocus(Qt.FocusReason.OtherFocusReason)

    def is_recording(self) -> bool:
        return self._recorder is not None

    def event(self, event: QEvent) -> bool:
        # While recording take Tab too, instead of moving the focus.
        if self._recorder is not None and event.type() == QEvent.Type.KeyPress:
            self.keyPressEvent(event)
            return True
        return super().event(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if self._recorder is None:
            super().keyPressEvent(event)
            return
        code = evdev_from_scancode(event.nativeScanCode())
        if code is not None and not event.isAutoRepeat():
            self._recorder.press(code)
        event.accept()

    def keyReleaseEvent(self, event: QKeyEvent) -> None:
        if self._recorder is None:
            super().keyReleaseEvent(event)
            return
        code = evdev_from_scancode(event.nativeScanCode())
        if code is None or event.isAutoRepeat():
            return
        combo = self._recorder.release(code)
        if combo:
            self._recorder = None
            self.setPlaceholderText(tr("dialog.keys_placeholder"))
            self.setText(format_keys(combo))
            self.recorded.emit()
        event.accept()


class MappingDialog(QDialog):
    def __init__(
        self, source: int, action: Action | None = None, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.source = source
        self.setWindowTitle(tr("dialog.title", button=button_label(source)))
        self.setMinimumWidth(460)
        self._build()
        self._load(action or Action((), Mode.HOLD))
        self._refresh()

    # --- layout ------------------------------------------------------------

    def _build(self) -> None:
        self.keys = KeysEdit()
        self.keys.textChanged.connect(self._refresh)
        self.keys.recorded.connect(self._refresh)
        record = QPushButton(tr("dialog.record"))
        record.clicked.connect(self.keys.start_recording)
        self.keys_help = QToolButton()
        self.keys_help.setText("?")
        self.keys_help.setToolTip(tr("dialog.keys_help"))
        self.keys_help.clicked.connect(self._show_keys_help)
        keys_row = QHBoxLayout()
        keys_row.addWidget(self.keys, 1)
        keys_row.addWidget(record)
        keys_row.addWidget(self.keys_help)
        self.keys_error = QLabel()
        self.keys_error.setStyleSheet("color: palette(link-visited);")

        self.mode_group = QButtonGroup(self)
        mode_box = QVBoxLayout()
        for index, mode in enumerate(MODES):
            radio = QRadioButton(tr(f"mode.{mode.value}_label"))
            self.mode_group.addButton(radio, index)
            if mode is Mode.REPEAT:
                self.count = QSpinBox()
                self.count.setRange(2, MAX_COUNT)
                row = QHBoxLayout()
                row.addWidget(radio)
                row.addWidget(self.count)
                row.addWidget(QLabel(tr("dialog.count")))
                row.addStretch(1)
                mode_box.addLayout(row)
            else:
                mode_box.addWidget(radio)
        self.mode_group.idToggled.connect(lambda *_: self._refresh())

        self.delay_fixed = QRadioButton(tr("dialog.delay_fixed"))
        self.delay_random = QRadioButton(tr("dialog.delay_random"))
        self.delay_fixed.toggled.connect(lambda *_: self._refresh())
        self.fixed_ms, self.low_ms, self.high_ms = (self._ms_spin() for _ in range(3))
        delay_grid = QGridLayout()
        delay_grid.addWidget(self.delay_fixed, 0, 0)
        delay_grid.addWidget(self.fixed_ms, 0, 1)
        delay_grid.addWidget(self.delay_random, 1, 0)
        delay_grid.addWidget(self.low_ms, 1, 1)
        delay_grid.addWidget(QLabel(tr("dialog.delay_and")), 1, 2)
        delay_grid.addWidget(self.high_ms, 1, 3)
        self.delay_hint = QLabel()
        self.delay_hint.setWordWrap(True)
        self.delay_widgets = [
            self.delay_fixed,
            self.delay_random,
            self.fixed_ms,
            self.low_ms,
            self.high_ms,
        ]

        self.tos = QLabel("⚠ " + tr("dialog.tos_warning"))
        self.tos.setWordWrap(True)

        form = QFormLayout()
        form.addRow(tr("dialog.keys"), keys_row)
        form.addRow("", self.keys_error)
        form.addRow(tr("dialog.mode"), mode_box)
        form.addRow(tr("dialog.delay"), delay_grid)
        form.addRow("", self.delay_hint)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.tos)
        layout.addWidget(self.buttons)

    @Slot()
    def _show_keys_help(self) -> None:
        below = self.keys_help.mapToGlobal(QPoint(0, self.keys_help.height()))
        QToolTip.showText(below, tr("dialog.keys_help"), self.keys_help)

    def _ms_spin(self) -> QSpinBox:
        spin = QSpinBox()
        spin.setRange(MIN_TIMED_DELAY_MS, MAX_DELAY_MS)
        spin.setSuffix(" ms")
        spin.setSingleStep(10)
        spin.valueChanged.connect(lambda *_: self._refresh())
        return spin

    def _load(self, action: Action) -> None:
        self.keys.setText(format_keys(action.keys) if action.keys else "")
        self.mode_group.button(MODES.index(action.mode)).setChecked(True)
        self.count.setValue(max(2, action.count))
        delay = action.delay
        low = max(delay.low_ms, MIN_TIMED_DELAY_MS)
        self.fixed_ms.setValue(low if not delay.is_random else DEFAULT_DELAY_MS)
        self.low_ms.setValue(low)
        self.high_ms.setValue(max(delay.high_ms, low))
        (self.delay_random if delay.is_random else self.delay_fixed).setChecked(True)

    # --- state ---------------------------------------------------------------

    def mode(self) -> Mode:
        return MODES[self.mode_group.checkedId()]

    def result_action(self) -> Action | None:
        """The action as entered, or None when it is not valid yet."""
        try:
            keys = parse_keys(self.keys.text())
        except ValueError:
            return None
        mode = self.mode()
        if self.delay_random.isChecked():
            if self.low_ms.value() > self.high_ms.value():
                return None
            delay = Delay(self.low_ms.value(), self.high_ms.value())
        else:
            delay = Delay(self.fixed_ms.value(), self.fixed_ms.value())
        if mode is Mode.HOLD:
            delay = Delay()
        count = self.count.value() if mode is Mode.REPEAT else 1
        return Action(keys, mode, count, delay)

    @Slot()
    def _refresh(self) -> None:
        mode = self.mode() if self.mode_group.checkedId() >= 0 else Mode.HOLD
        timed = mode is not Mode.HOLD
        for widget in self.delay_widgets:
            widget.setEnabled(timed)
        random_delay = self.delay_random.isChecked()
        self.fixed_ms.setEnabled(timed and not random_delay)
        self.low_ms.setEnabled(timed and random_delay)
        self.high_ms.setEnabled(timed and random_delay)
        self.count.setEnabled(mode is Mode.REPEAT)
        self.delay_hint.setText(
            ""
            if not timed
            else tr("dialog.delay_hint_once" if mode is Mode.ONCE else "dialog.delay_hint_loop")
        )
        self.tos.setVisible(mode in (Mode.TOGGLE, Mode.REPEAT))

        error = ""
        text = self.keys.text().strip()
        if text and not self.keys.is_recording():
            try:
                parse_keys(text)
            except ValueError as exc:
                error = tr("dialog.keys_invalid", detail=str(exc))
        self.keys_error.setText(error)
        self.keys_error.setVisible(bool(error))
        ok = self.buttons.button(QDialogButtonBox.StandardButton.Ok)
        ok.setEnabled(self.result_action() is not None)
        self._fit_height()

    def _fit_height(self) -> None:
        """Grow to fit texts that appear or wrap after the dialog is open.

        Qt only sets a top-level minimum from minimumSize(), which ignores how
        tall word-wrapped labels get at the current width, so they would be cut.
        """
        layout = self.layout()
        if layout is None:
            return
        layout.activate()
        need = layout.totalHeightForWidth(self.width()) if layout.hasHeightForWidth() else 0
        if need > self.height():
            self.resize(self.width(), need)
