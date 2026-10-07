"""Main window: one on/off switch, profiles per game, one row per mouse button, optional log."""

import dataclasses
from collections import deque
from collections.abc import Callable
from pathlib import Path
from typing import Any

from PySide6.QtCore import QEvent, QObject, QSignalBlocker, QSize, Qt, QUrl, Slot
from PySide6.QtGui import QDesktopServices, QFont, QIcon
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from linmbc import i18n
from linmbc.games import Game, installed_steam_games
from linmbc.gui.game_dialog import GameDialog
from linmbc.gui.mapping_dialog import STANDARD_BUTTONS, MappingDialog, button_label
from linmbc.gui.mouse_icons import button_icon
from linmbc.gui.profile_list import ProfileList
from linmbc.gui.settings import GuiSettings, ordered, save_settings
from linmbc.i18n import tr
from linmbc.keynames import format_keys
from linmbc.keys import code_of
from linmbc.profile import Action, Mode, Profile
from linmbc.profile_store import ProfileStore

DEFAULT_PROFILE = "Default"  # internal name of the profile used outside games
LOGO = Path(__file__).resolve().parent.parent / "icons" / "linmbc.svg"
LOG_LINES = 2000
LOG_TAIL_ON_START = 200
COLUMNS = ("button", "keys", "mode", "delay")
LEFT = code_of("BTN_LEFT")
ROW_ICON = 32
FLAG_W, FLAG_H = 20, 15  # flag-icons are 4:3


def icon_button(theme_icon: str, fallback: str, tooltip: str) -> QToolButton:
    """Small icon-only button; the text glyph is used when the icon theme lacks it."""
    button = QToolButton()
    icon = QIcon.fromTheme(theme_icon)
    if icon.isNull():
        button.setText(fallback)
    else:
        button.setIcon(icon)
    button.setToolTip(tooltip)
    button.setAutoRaise(True)
    return button


def describe_mode(action: Action) -> str:
    if action.mode is Mode.REPEAT:
        return tr("mode.repeat", count=action.count)
    return tr(f"mode.{action.mode.value}")


def describe_delay(action: Action) -> str:
    if action.mode is Mode.HOLD:
        return tr("delay.none")
    delay = action.delay
    if delay.is_random:
        return tr("delay.random", low=delay.low_ms, high=delay.high_ms)
    return tr("delay.fixed", ms=delay.low_ms)


class MainWindow(QMainWindow):
    def __init__(
        self,
        client: Any,
        store: ProfileStore,
        settings: GuiSettings,
        settings_path: Path,
        games: Callable[[], list[Game]] = installed_steam_games,
    ) -> None:
        super().__init__()
        self.client = client
        self.store = store
        self.settings = settings
        self.settings_path = settings_path
        self.games = games
        self.state: dict[str, Any] = {}
        self._default_sent = False
        self.log_lines: deque[str] = deque(maxlen=LOG_LINES)
        self.setWindowIcon(QIcon(str(LOGO)))
        self.resize(1000, 620)
        self._build()
        client.state_changed.connect(self.apply_state)
        client.log_line.connect(self.append_log)
        client.available_changed.connect(lambda _up: self._show_status())
        client.error.connect(lambda msg: self.append_log(tr("error.dbus", message=msg)))
        if client.is_available():
            client.refresh()

    # --- layout ------------------------------------------------------------

    def _build(self) -> None:
        self.setWindowTitle(tr("app.title"))
        root = QWidget()
        layout = QVBoxLayout(root)
        layout.addLayout(self._build_top())
        body = QHBoxLayout()
        body.addLayout(self._build_profiles())
        body.addLayout(self._build_buttons(), 1)
        layout.addLayout(body, 1)
        layout.addWidget(self._build_log())
        self.setCentralWidget(root)
        self._fill_profiles()
        self._show_status()

    def _build_top(self) -> QHBoxLayout:
        self.toggle = QPushButton()
        self.toggle.setCheckable(True)
        self.toggle.setMinimumWidth(120)
        self.toggle.setToolTip(tr("toggle.tooltip"))
        bold = QFont()
        bold.setBold(True)
        self.toggle.setFont(bold)
        self.toggle.toggled.connect(self._toggled)
        self.status = QLabel()
        self.status.setWordWrap(True)
        self.language = QComboBox()
        self.language.setIconSize(QSize(FLAG_W, FLAG_H))
        self.language.addItem(
            QIcon.fromTheme("preferences-desktop-locale"), tr("language.auto"), i18n.AUTO
        )
        for code, name in i18n.LANGUAGES.items():
            # SVG icons are vector, so flags stay sharp on scaled screens
            self.language.addItem(QIcon(str(i18n.flag_path(code))), name, code)
        self.language.setCurrentIndex(max(0, self.language.findData(self.settings.language)))
        self.language.activated.connect(self._language_chosen)
        top = QHBoxLayout()
        top.addWidget(self.toggle)
        top.addWidget(self.status, 1)
        top.addWidget(QLabel(tr("language.label")))
        top.addWidget(self.language)
        return top

    def _build_profiles(self) -> QVBoxLayout:
        self.profiles = ProfileList(DEFAULT_PROFILE)
        self.profiles.setMaximumWidth(260)
        self.profiles.currentItemChanged.connect(lambda *_: self._show_profile())
        self.profiles.remove_requested.connect(self._remove_profile)
        self.profiles.order_changed.connect(self._order_changed)
        add = QPushButton(tr("profiles.add"))
        add.clicked.connect(self._add_profile)
        left = QVBoxLayout()
        left.addWidget(QLabel(f"<b>{tr('profiles.title')}</b>"))
        left.addWidget(self.profiles, 1)
        left.addWidget(add)
        return left

    def _build_buttons(self) -> QVBoxLayout:
        self.profile_title = QLabel()
        self.window_label = QLabel(tr("profile.window_label"))
        self.window_edit = QLineEdit()
        self.window_edit.setToolTip(tr("profile.window_hint"))
        self.window_edit.editingFinished.connect(self._window_edited)
        self.window_note = QLabel(tr("profile.window_default"))
        self.window_note.setWordWrap(True)
        window_row = QHBoxLayout()
        window_row.addWidget(self.window_label)
        window_row.addWidget(self.window_edit, 1)
        self.table = QTableWidget(0, len(COLUMNS) + 1)
        self.table.setHorizontalHeaderLabels([tr(f"mapping.col_{c}") for c in COLUMNS] + [""])
        header = self.table.horizontalHeader()
        # Columns fit their content and never wrap, so no text is cut with "…".
        # The keys column (the only free text) also takes the spare width; see
        # _fit_keys_column. Every cell has a tooltip.
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(COLUMNS.index("keys"), QHeaderView.ResizeMode.Fixed)
        header.setStretchLastSection(False)
        self.table.setWordWrap(False)
        self.table.viewport().installEventFilter(self)
        self.table.setIconSize(QSize(ROW_ICON, ROW_ICON))
        self.table.verticalHeader().setDefaultSectionSize(ROW_ICON + 10)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.table.cellDoubleClicked.connect(self._row_double_clicked)
        right = QVBoxLayout()
        right.addWidget(self.profile_title)
        right.addLayout(window_row)
        right.addWidget(self.window_note)
        right.addWidget(self.table, 1)
        return right

    def _build_log(self) -> QGroupBox:
        self.log_box = QGroupBox(tr("log.title"))
        self.log_box.setCheckable(True)
        self.log_box.setChecked(False)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(LOG_LINES)
        self.log.setPlainText("\n".join(self.log_lines))
        open_log = QPushButton(tr("log.open_file"))
        open_log.clicked.connect(self._open_log_file)
        log_layout = QVBoxLayout(self.log_box)
        log_layout.addWidget(self.log)
        log_layout.addWidget(open_log, 0, Qt.AlignmentFlag.AlignRight)
        self.log_box.toggled.connect(self.log.setVisible)
        self.log_box.toggled.connect(open_log.setVisible)
        self.log.setVisible(False)
        open_log.setVisible(False)
        return self.log_box

    # --- daemon state --------------------------------------------------------

    @Slot(dict)
    def apply_state(self, state: dict[str, Any]) -> None:
        first = not self.state
        buttons_changed = state.get("buttons") != self.state.get("buttons")
        self.state = state
        if first and state.get("log_path"):
            self._load_log_tail(Path(state["log_path"]))
        if self.store.list().get(DEFAULT_PROFILE):
            self._ensure_default()
        self._show_status()
        self.profiles.mark_active(state.get("active_profile", ""))
        if buttons_changed:
            self._show_profile()

    def _ensure_default(self) -> None:
        """Make the daemon use our Default profile outside games; ask once per session."""
        if self._default_sent or self.state.get("default_profile") == DEFAULT_PROFILE:
            return
        self._default_sent = True
        self.client.set_default_profile(DEFAULT_PROFILE)

    def _show_status(self) -> None:
        available = self.client.is_available()
        enabled = bool(self.state.get("enabled")) and available
        with QSignalBlocker(self.toggle):
            self.toggle.setChecked(enabled)
        self.toggle.setText(tr("toggle.on" if enabled else "toggle.off"))
        self.toggle.setEnabled(available)
        if not available:
            self.status.setText(tr("status.daemon_missing"))
            return
        mice = self.state.get("mice") or []
        lines = [tr("status.mice", names=", ".join(mice)) if mice else tr("status.no_mouse")]
        if self.state.get("window_class"):
            profile = self._display_name(self.state.get("active_profile", ""))
            lines.append(tr("status.window", window=self.state["window_class"], profile=profile))
        self.status.setText("\n".join(lines))

    def _display_name(self, name: str) -> str:
        if not name:
            return tr("status.no_profile")
        return tr("profiles.default") if name == DEFAULT_PROFILE else name

    # --- profiles --------------------------------------------------------------

    def _fill_profiles(self, select: str | None = None) -> None:
        games = [n for n in self.store.list() if n != DEFAULT_PROFILE]
        names = ordered(games, self.settings.profile_order)
        labels = {DEFAULT_PROFILE: self._display_name(DEFAULT_PROFILE)}
        self.profiles.fill(names, labels, select or self.profiles.selected_name())
        self.profiles.mark_active(self.state.get("active_profile", ""))
        self._show_profile()

    def selected_profile(self) -> Profile:
        name = self.profiles.selected_name() or DEFAULT_PROFILE
        return self.store.list().get(name) or Profile(name=name)

    @Slot()
    def _add_profile(self) -> None:
        dialog = GameDialog(self.games(), set(self.store.list()), self)
        if dialog.exec() != GameDialog.DialogCode.Accepted:
            return
        game = dialog.chosen()
        if game is not None and self._save(Profile(name=game.name, match=game.match), None):
            self._fill_profiles(select=game.name)

    @Slot(str)
    def _remove_profile(self, name: str) -> None:
        if name == DEFAULT_PROFILE or name not in self.store.list():
            return
        answer = QMessageBox.question(
            self, tr("profiles.remove"), tr("profiles.remove_confirm", name=name)
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.remove_profile_now(name)

    def remove_profile_now(self, name: str) -> None:
        selected = self.profiles.selected_name()
        self.store.delete(name)
        self.client.reload_profiles()
        self._fill_profiles(select=DEFAULT_PROFILE if selected == name else selected)

    @Slot(list)
    def _order_changed(self, names: list[str]) -> None:
        self.settings = dataclasses.replace(self.settings, profile_order=tuple(names))
        save_settings(self.settings, self.settings_path)
        self._fill_profiles()  # rebuild row widgets the drag may have dropped

    @Slot()
    def _window_edited(self) -> None:
        profile = self.selected_profile()
        match = tuple(w.strip() for w in self.window_edit.text().split(",") if w.strip())
        if profile.name != DEFAULT_PROFILE and match != profile.match:
            self._save(dataclasses.replace(profile, match=match), profile.name)

    # --- button rows -----------------------------------------------------------

    def button_codes(self) -> list[int]:
        """The detected mouse's buttons (or the standard 5), plus any already configured."""
        detected = [code_of(n) for n in self.state.get("buttons") or []]
        codes = set(detected or STANDARD_BUTTONS) | set(self.selected_profile().buttons)
        return sorted(codes)

    def _show_profile(self) -> None:
        profile = self.selected_profile()
        is_default = profile.name == DEFAULT_PROFILE
        self.profile_title.setText(f"<b>{self._display_name(profile.name)}</b>")
        self.window_label.setVisible(not is_default)
        self.window_edit.setVisible(not is_default)
        self.window_edit.setText(", ".join(profile.match))
        self.window_note.setVisible(is_default)
        codes = self.button_codes()
        self._drop_row_widgets()
        self.table.setRowCount(len(codes))
        for row, code in enumerate(codes):
            action = profile.buttons.get(code)
            cells = [button_label(code), tr("mapping.none"), "", ""]
            if action is not None:
                cells[1:] = [
                    format_keys(action.keys),
                    describe_mode(action),
                    describe_delay(action),
                ]
            for col, text in enumerate(cells):
                item = QTableWidgetItem(text)
                item.setData(Qt.ItemDataRole.UserRole, code)
                item.setToolTip(text)
                if col == 0:
                    item.setIcon(button_icon(code, ROW_ICON))
                    font = item.font()
                    font.setBold(action is not None)
                    item.setFont(font)
                self.table.setItem(row, col, item)
            self.table.setCellWidget(row, len(COLUMNS), self._row_buttons(code, action, is_default))
        self.table.resizeColumnsToContents()
        self._fit_keys_column()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.Type.Resize and watched is self.table.viewport():
            self._fit_keys_column()
        return super().eventFilter(watched, event)

    def _fit_keys_column(self) -> None:
        """Keys get whatever width is left, but never less than their longest text."""
        keys = COLUMNS.index("keys")
        others = sum(
            self.table.columnWidth(c) for c in range(self.table.columnCount()) if c != keys
        )
        need = max(
            self.table.sizeHintForColumn(keys),
            self.table.horizontalHeader().sectionSizeHint(keys),
        )
        self.table.setColumnWidth(keys, max(need, self.table.viewport().width() - others))

    def _drop_row_widgets(self) -> None:
        """Qt deletes replaced cell widgets later; hide them now so none is drawn at (0, 0)."""
        for row in range(self.table.rowCount()):
            widget = self.table.cellWidget(row, len(COLUMNS))
            if widget is not None:
                widget.hide()
                self.table.removeCellWidget(row, len(COLUMNS))

    def _row_buttons(self, code: int, action: Action | None, is_default: bool) -> QWidget:
        configure = icon_button("configure", "⚙", tr("mapping.configure"))
        configure.clicked.connect(lambda _=False, c=code: self.configure_button(c))
        clear = icon_button("edit-clear", "✕", tr("mapping.clear"))
        clear.setEnabled(action is not None)
        clear.clicked.connect(lambda _=False, c=code: self.clear_button(c))
        if code == LEFT and is_default:
            configure.setEnabled(False)
            configure.setToolTip(tr("mapping.left_blocked"))
        box = QWidget()
        layout = QHBoxLayout(box)
        layout.setContentsMargins(2, 0, 6, 0)
        layout.addWidget(configure)
        layout.addWidget(clear)
        return box

    def _row_double_clicked(self, row: int, _col: int) -> None:
        item = self.table.item(row, 0)
        if item is None:
            return
        code = item.data(Qt.ItemDataRole.UserRole)
        if not (code == LEFT and self.selected_profile().name == DEFAULT_PROFILE):
            self.configure_button(code)

    def configure_button(self, code: int) -> None:
        dialog = MappingDialog(code, self.selected_profile().buttons.get(code), self)
        if dialog.exec() != MappingDialog.DialogCode.Accepted:
            return
        action = dialog.result_action()
        if action is not None:
            self.set_mapping(code, action)

    def set_mapping(self, code: int, action: Action) -> None:
        profile = self.selected_profile()
        if code == LEFT and profile.name == DEFAULT_PROFILE:
            return  # outside games a remapped left button leaves the desktop without clicks
        buttons = {**profile.buttons, code: action}
        self._save(dataclasses.replace(profile, buttons=buttons), profile.name)

    def clear_button(self, code: int) -> None:
        profile = self.selected_profile()
        buttons = {c: a for c, a in profile.buttons.items() if c != code}
        self._save(dataclasses.replace(profile, buttons=buttons), profile.name)

    def _save(self, profile: Profile, previous_name: str | None) -> bool:
        exists = previous_name in self.store.list() if previous_name else False
        try:
            self.store.save(profile, previous_name=previous_name if exists else None)
        except ValueError as exc:
            QMessageBox.warning(self, tr("app.title"), str(exc))
            return False
        self.client.reload_profiles()
        if profile.name == DEFAULT_PROFILE:
            self._ensure_default()
        self._show_profile()
        return True

    # --- on/off, language, log --------------------------------------------------

    @Slot(bool)
    def _toggled(self, on: bool) -> None:
        self.client.set_enabled(on)
        self.toggle.setText(tr("toggle.on" if on else "toggle.off"))

    @Slot(int)
    def _language_chosen(self, _index: int) -> None:
        setting = self.language.currentData()
        self.settings = dataclasses.replace(self.settings, language=setting)
        save_settings(self.settings, self.settings_path)
        i18n.set_language(i18n.resolve(setting, i18n.system_locale()))
        selected = self.profiles.selected_name()
        self._build()
        self._fill_profiles(select=selected)
        self._show_status()

    @Slot(str)
    def append_log(self, line: str) -> None:
        self.log_lines.append(line)
        self.log.appendPlainText(line)

    def _load_log_tail(self, path: Path) -> None:
        try:
            with path.open(encoding="utf-8", errors="replace") as handle:
                lines = deque(handle, maxlen=LOG_TAIL_ON_START)
        except OSError:
            return
        self.log_lines.extend(line.rstrip("\n") for line in lines)
        self.log.setPlainText("\n".join(self.log_lines))

    @Slot()
    def _open_log_file(self) -> None:
        path = self.state.get("log_path")
        if path:
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))
