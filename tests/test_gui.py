import pytest

pytest.importorskip("PySide6")

from evdev import ecodes as e  # noqa: E402
from PySide6.QtCore import QEvent, QModelIndex, QObject, QSize, Qt, Signal  # noqa: E402
from PySide6.QtGui import QKeyEvent  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QApplication,
    QDialogButtonBox,
    QMessageBox,
    QToolButton,
)

from linmbc import i18n  # noqa: E402
from linmbc.games import Game  # noqa: E402
from linmbc.gui.game_dialog import GameDialog  # noqa: E402
from linmbc.gui.main_window import COLUMNS, DEFAULT_PROFILE, MainWindow  # noqa: E402
from linmbc.gui.mapping_dialog import MODES, MappingDialog  # noqa: E402
from linmbc.gui.settings import GuiSettings, load_settings  # noqa: E402
from linmbc.profile import Action, Delay, Mode, Profile, load  # noqa: E402
from linmbc.profile_store import ProfileStore  # noqa: E402

LAST_EPOCH = Game("Last Epoch", ("steam_app_899770",))
FIVE = ["BTN_LEFT", "BTN_RIGHT", "BTN_MIDDLE", "BTN_SIDE", "BTN_EXTRA"]


class FakeClient(QObject):
    state_changed = Signal(dict)
    log_line = Signal(str)
    button = Signal(str, str, int)
    available_changed = Signal(bool)
    error = Signal(str)

    def __init__(self):
        super().__init__()
        self.calls = []

    def is_available(self):
        return True

    def refresh(self):
        self.calls.append(("refresh",))

    def set_enabled(self, enabled):
        self.calls.append(("set_enabled", enabled))

    def set_default_profile(self, name):
        self.calls.append(("set_default_profile", name))

    def reload_profiles(self):
        self.calls.append(("reload_profiles",))

    def quit_daemon(self):
        self.calls.append(("quit_daemon",))

    def start_daemon(self):
        return True


def state(**overrides):
    base = {
        "enabled": False,
        "default_profile": "",
        "active_profile": "",
        "window_class": "firefox",
        "profiles": [],
        "mice": ["WL WLMOUSE MINI PRO 8K RECEIVER"],
        "buttons": FIVE,
        "log_path": "",
    }
    return {**base, **overrides}


@pytest.fixture(autouse=True)
def english():
    i18n.set_language("en")
    yield
    i18n.set_language("en")


def make_window(qtbot, tmp_path, settings=None):
    client = FakeClient()
    win = MainWindow(
        client,
        ProfileStore(tmp_path / "profiles"),
        settings or GuiSettings(),
        tmp_path / "gui.toml",
        games=lambda: [LAST_EPOCH],
    )
    qtbot.addWidget(win)
    client.state_changed.emit(state())
    client.calls.clear()
    return win


@pytest.fixture
def window(qtbot, tmp_path):
    return make_window(qtbot, tmp_path)


def select(win, name):
    for row in range(win.profiles.count()):
        if win.profiles.item(row).data(Qt.ItemDataRole.UserRole) == name:
            win.profiles.setCurrentRow(row)
            return
    raise AssertionError(name)


def add_game(win, name, match=()):
    win._save(Profile(name=name, match=match), None)
    win._fill_profiles(select=name)


def rows(win):
    return [
        [win.table.item(r, c).text() for c in range(len(COLUMNS))]
        for r in range(win.table.rowCount())
    ]


def row_buttons(win, row):
    box = win.table.cellWidget(row, len(COLUMNS))
    configure, clear = box.findChildren(QToolButton)
    return configure, clear


# --- top bar -------------------------------------------------------------------


def test_status_shows_detected_mouse_and_focused_window(window):
    text = window.status.text()
    assert "WL WLMOUSE MINI PRO 8K RECEIVER" in text
    assert "firefox" in text


def test_toggle_follows_state_without_echo_and_sends_clicks(window):
    window.client.state_changed.emit(state(enabled=True))
    assert window.toggle.isChecked() and window.toggle.text() == "On"
    assert window.client.calls == []
    window.toggle.click()
    assert window.client.calls == [("set_enabled", False)]


# --- button rows ----------------------------------------------------------------


def test_every_mouse_button_has_a_row_without_adding_anything(window):
    assert [r[0] for r in rows(window)] == [
        "Left",
        "Right",
        "Middle (wheel)",
        "Side — rear",
        "Side — front",
    ]
    assert all(r[1] == "Unchanged" for r in rows(window))


def test_rows_follow_the_buttons_the_mouse_has(window):
    window.client.state_changed.emit(state(buttons=[*FIVE, "BTN_FORWARD", "BTN_BACK"]))
    assert len(rows(window)) == 7
    assert rows(window)[-1][0] == "Back"


def test_configuring_a_row_saves_and_shows_the_action(window, tmp_path):
    action = Action((e.KEY_LEFTCTRL, e.KEY_2), Mode.TOGGLE, delay=Delay(100, 900))
    window.set_mapping(e.BTN_SIDE, action)
    assert load(tmp_path / "profiles/default.toml").buttons == {e.BTN_SIDE: action}
    assert ("set_default_profile", DEFAULT_PROFILE) in window.client.calls
    assert rows(window)[3] == [
        "Side — rear",
        "Ctrl+2",
        "Loop until clicked again",
        "100–900 ms (random)",
    ]
    _, clear = row_buttons(window, 3)
    assert clear.isEnabled()


def test_clear_returns_the_button_to_normal(window, tmp_path):
    window.set_mapping(e.BTN_SIDE, Action((e.KEY_1,)))
    window.clear_button(e.BTN_SIDE)
    assert load(tmp_path / "profiles/default.toml").buttons == {}
    assert rows(window)[3][1] == "Unchanged"


def test_left_button_is_locked_outside_games_but_allowed_in_a_game(window, tmp_path):
    configure, _ = row_buttons(window, 0)
    assert not configure.isEnabled()
    window.set_mapping(e.BTN_LEFT, Action((e.KEY_1,)))
    assert not (tmp_path / "profiles/default.toml").exists()

    add_game(window, "Last Epoch", ("steam_app_899770",))
    configure, _ = row_buttons(window, 0)
    assert configure.isEnabled()
    window.set_mapping(e.BTN_LEFT, Action((e.KEY_1,)))
    assert e.BTN_LEFT in load(tmp_path / "profiles/last-epoch.toml").buttons


def test_rows_have_icons_tooltips_and_icon_only_actions(window):
    window.set_mapping(e.BTN_SIDE, Action((e.KEY_1,), Mode.TOGGLE, delay=Delay(100, 900)))
    for row in range(window.table.rowCount()):
        assert not window.table.item(row, 0).icon().isNull()
        for col in range(len(COLUMNS)):
            item = window.table.item(row, col)
            assert item.toolTip() == item.text()
        configure, clear = row_buttons(window, row)
        locked = row == 0  # left button in Default: the tooltip says why it is locked
        expected = i18n.tr("mapping.left_blocked") if locked else "Configure"
        assert configure.toolTip() == expected and clear.toolTip() == "Clear"
        assert configure.text() in ("", "⚙") and clear.text() in ("", "✕")


def test_keys_column_takes_the_spare_width_and_never_less_than_its_text(window):
    window.set_mapping(e.BTN_SIDE, Action((e.KEY_LEFTCTRL, e.KEY_LEFTSHIFT, e.KEY_A, e.KEY_F12)))
    window.show()
    table = window.table
    keys = COLUMNS.index("keys")
    actions = len(COLUMNS)
    header = table.horizontalHeader()
    assert not table.wordWrap()
    assert not header.stretchLastSection()

    window.resize(1400, 620)
    QApplication.processEvents()
    widths = [table.columnWidth(c) for c in range(len(COLUMNS) + 1)]
    assert sum(widths) == table.viewport().width()  # the table is filled...
    assert widths[actions] == table.sizeHintForColumn(actions)  # ...but not by the icons
    assert widths[keys] > table.sizeHintForColumn(keys)  # the spare width went to keys

    window.resize(500, 620)  # too narrow: keys keep their text, a scrollbar appears
    QApplication.processEvents()
    assert table.columnWidth(keys) >= table.sizeHintForColumn(keys)
    for col in range(len(COLUMNS) + 1):
        assert table.columnWidth(col) >= table.sizeHintForColumn(col), col


def test_configured_button_missing_from_the_mouse_still_shows(window):
    window.set_mapping(e.BTN_FORWARD, Action((e.KEY_1,)))
    assert "Forward" in [r[0] for r in rows(window)]


def test_window_class_edit_is_saved(window, tmp_path):
    add_game(window, "Last Epoch", ("steam_app_899770",))
    window.window_edit.setText("steam_app_899770, last epoch.exe")
    window._window_edited()
    assert load(tmp_path / "profiles/last-epoch.toml").match == (
        "steam_app_899770",
        "last epoch.exe",
    )


def test_default_profile_is_requested_once_per_session(window):
    window.set_mapping(e.BTN_SIDE, Action((e.KEY_1,)))
    window.set_mapping(e.BTN_EXTRA, Action((e.KEY_2,)))
    window.client.state_changed.emit(state())
    assert window.client.calls.count(("set_default_profile", DEFAULT_PROFILE)) == 1


# --- profile list ----------------------------------------------------------------


def test_default_is_pinned_first_without_trash_and_games_have_one(window):
    add_game(window, "Last Epoch")
    assert window.profiles.names() == [DEFAULT_PROFILE, "Last Epoch"]
    assert window.profiles.row_widget(DEFAULT_PROFILE).trash is None
    assert window.profiles.row_widget("Last Epoch").trash is not None
    default_item = window.profiles.item(0)
    assert not (default_item.flags() & Qt.ItemFlag.ItemIsDragEnabled)


def test_trash_confirms_then_removes_that_profile(window, tmp_path, monkeypatch):
    from linmbc.gui import main_window

    add_game(window, "Last Epoch")
    answers = [QMessageBox.StandardButton.No, QMessageBox.StandardButton.Yes]
    monkeypatch.setattr(main_window.QMessageBox, "question", lambda *a: answers.pop(0))

    window.profiles.row_widget("Last Epoch").trash.click()  # answered No
    assert (tmp_path / "profiles/last-epoch.toml").exists()
    window.profiles.row_widget("Last Epoch").trash.click()  # answered Yes
    assert window.profiles.names() == [DEFAULT_PROFILE]
    assert not (tmp_path / "profiles/last-epoch.toml").exists()


def test_dragging_reorders_and_the_order_is_saved(window, tmp_path):
    for name in ("Hero Siege", "Last Epoch", "Path of Exile 2"):
        add_game(window, name)
    assert window.profiles.names()[1:] == ["Hero Siege", "Last Epoch", "Path of Exile 2"]
    # what a drop does: move "Path of Exile 2" (row 3) above "Hero Siege" (row 1)
    window.profiles.model().moveRows(QModelIndex(), 3, 1, QModelIndex(), 1)
    expected = ["Path of Exile 2", "Hero Siege", "Last Epoch"]
    assert window.profiles.names() == [DEFAULT_PROFILE, *expected]
    assert load_settings(tmp_path / "gui.toml").profile_order == tuple(expected)
    assert all(window.profiles.row_widget(n) is not None for n in expected)


def test_saved_order_is_used_when_the_window_opens(qtbot, tmp_path):
    store = ProfileStore(tmp_path / "profiles")
    for name in ("A", "B", "C"):
        store.save(Profile(name=name))
    win = make_window(qtbot, tmp_path, GuiSettings(profile_order=("C", "A")))
    assert win.profiles.names() == [DEFAULT_PROFILE, "C", "A", "B"]


def test_active_profile_is_bold_in_the_list(window):
    add_game(window, "Last Epoch")
    window.client.state_changed.emit(state(active_profile="Last Epoch"))
    assert window.profiles.row_widget("Last Epoch").label.font().bold()
    assert not window.profiles.row_widget(DEFAULT_PROFILE).label.font().bold()


def test_language_change_rebuilds_texts_and_is_saved(window, tmp_path):
    window.language.setCurrentIndex(window.language.findData("pt_BR"))
    window._language_chosen(0)
    assert window.toggle.text() == "Desligado"
    assert window.profiles.row_widget(DEFAULT_PROFILE).label.text() == "Padrão (fora dos jogos)"
    assert rows(window)[3][0] == "Lateral de trás"
    assert load_settings(tmp_path / "gui.toml").language == "pt_BR"


def test_log_lines_are_kept_while_the_log_is_collapsed(window):
    window.client.log_line.emit("12:00:00 BTN_SIDE down -> KEY_1 down [x] 0.20 ms")
    assert not window.log_box.isChecked()
    assert "KEY_1 down" in window.log.toPlainText()


# --- mapping dialog ------------------------------------------------------------


def key_event(kind, scancode):
    return QKeyEvent(kind, Qt.Key.Key_unknown, Qt.KeyboardModifier.NoModifier, scancode, 0, 0)


@pytest.fixture
def dialog(qtbot):
    dlg = MappingDialog(e.BTN_SIDE)
    qtbot.addWidget(dlg)
    return dlg


def ok_enabled(dlg):
    return dlg.buttons.button(QDialogButtonBox.StandardButton.Ok).isEnabled()


def set_mode(dlg, mode):
    dlg.mode_group.button(MODES.index(mode)).setChecked(True)


def test_dialog_is_for_one_button(dialog):
    assert dialog.windowTitle() == "Configure: Side — rear"
    assert dialog.source == e.BTN_SIDE


def test_dialog_accepts_typed_keys_and_rejects_garbage(dialog):
    dialog.keys.setText("Ctrl+2")
    assert ok_enabled(dialog)
    assert dialog.result_action() == Action((e.KEY_LEFTCTRL, e.KEY_2))
    dialog.keys.setText("Ctrl+Banana")
    assert not ok_enabled(dialog)
    assert dialog.keys_error.isVisibleTo(dialog)


def test_dialog_records_keys_from_scancodes(dialog):
    dialog.keys.start_recording()
    for kind, scancode in [
        (QEvent.Type.KeyPress, 37),  # left ctrl
        (QEvent.Type.KeyPress, 11),  # 2
        (QEvent.Type.KeyRelease, 11),
        (QEvent.Type.KeyRelease, 37),
    ]:
        QApplication.sendEvent(dialog.keys, key_event(kind, scancode))
    assert dialog.keys.text() == "Ctrl+2"
    assert not dialog.keys.is_recording()


def test_dialog_tos_warning_only_for_loop_and_repeat(dialog):
    dialog.keys.setText("Q")
    for mode, warned in [
        (Mode.HOLD, False),
        (Mode.ONCE, False),
        (Mode.TOGGLE, True),
        (Mode.REPEAT, True),
    ]:
        set_mode(dialog, mode)
        assert dialog.tos.isVisibleTo(dialog) is warned, mode


def test_dialog_builds_repeat_with_random_delay(dialog):
    dialog.keys.setText("F1")
    set_mode(dialog, Mode.REPEAT)
    dialog.count.setValue(5)
    dialog.delay_random.setChecked(True)
    dialog.low_ms.setValue(100)
    dialog.high_ms.setValue(900)
    assert dialog.result_action() == Action((e.KEY_F1,), Mode.REPEAT, 5, Delay(100, 900))
    dialog.low_ms.setValue(950)
    assert not ok_enabled(dialog)


def test_dialog_hold_has_no_delay(dialog):
    dialog.keys.setText("Q")
    set_mode(dialog, Mode.HOLD)
    assert not dialog.fixed_ms.isEnabled()
    assert dialog.result_action() == Action((e.KEY_Q,))


def test_dialog_edits_existing_action(qtbot):
    action = Action((e.KEY_E,), Mode.ONCE, delay=Delay(80, 80))
    dlg = MappingDialog(e.BTN_MIDDLE, action)
    qtbot.addWidget(dlg)
    assert dlg.result_action() == action


# --- game dialog ----------------------------------------------------------------


def test_game_dialog_lists_games_and_disables_taken_ones(qtbot):
    games = [LAST_EPOCH, Game("Path of Exile 2", ("steam_app_2694490",))]
    dlg = GameDialog(games, taken={"Last Epoch"})
    qtbot.addWidget(dlg)
    assert dlg.windowTitle() == "Add profile"
    assert not (dlg.games.item(0).flags() & Qt.ItemFlag.ItemIsEnabled)
    dlg.games.setCurrentRow(1)
    assert dlg.chosen() == games[1]


def test_game_dialog_other_application_needs_name_and_window(qtbot):
    dlg = GameDialog([], taken=set())
    qtbot.addWidget(dlg)
    assert dlg.other.isChecked()
    dlg.name.setText("Grim Dawn")
    assert dlg.chosen() is None
    dlg.window.setText("steam_app_219990, grim dawn.exe")
    assert dlg.chosen() == Game("Grim Dawn", ("steam_app_219990", "grim dawn.exe"))


def test_dialog_accepts_letters_pressed_together_and_has_help(dialog):
    dialog.keys.setText("er")
    assert dialog.result_action() == Action((e.KEY_E, e.KEY_R))
    assert ok_enabled(dialog)
    assert "E+R" in dialog.keys_help.toolTip()
    dialog.keys_help.click()  # shows the same text as a tooltip; must not block


def test_redrawing_rows_leaves_no_stray_action_widgets(window):
    from PySide6.QtWidgets import QWidget

    window.show()
    for _ in range(3):
        window._show_profile()
    QApplication.processEvents()
    current = {window.table.cellWidget(r, len(COLUMNS)) for r in range(window.table.rowCount())}
    viewport = window.table.viewport()
    strays = [
        w
        for w in viewport.findChildren(QWidget)
        if w.parent() is viewport and w not in current and w.isVisible()
    ]
    assert strays == []


def clipped_labels(widget):
    """Visible labels shorter than their text needs (word-wrapped text cut at the bottom)."""
    from PySide6.QtWidgets import QLabel

    cut = []
    for label in widget.findChildren(QLabel):
        if not label.isVisible() or not label.text():
            continue
        need = (
            label.heightForWidth(label.width()) if label.wordWrap() else label.sizeHint().height()
        )
        if label.height() < need:
            cut.append((label.text()[:40], label.height(), need))
    return cut


@pytest.mark.parametrize("start", MODES)
@pytest.mark.parametrize("language", ["en", "de", "pt_BR"])
def test_dialog_never_cuts_text_when_switching_modes(qtbot, start, language):
    i18n.set_language(language)
    dlg = MappingDialog(e.BTN_MIDDLE, Action((e.KEY_E, e.KEY_R), start, 2, Delay(1500, 1500)))
    qtbot.addWidget(dlg)
    dlg.show()
    QApplication.processEvents()
    for mode in MODES:
        set_mode(dlg, mode)
        QApplication.processEvents()
        assert clipped_labels(dlg) == [], (start, mode)


@pytest.mark.parametrize("language", list(i18n.LANGUAGES))
def test_main_window_and_dialogs_never_cut_text(qtbot, tmp_path, language):
    i18n.set_language(language)
    win = make_window(qtbot, tmp_path)
    win.show()
    QApplication.processEvents()
    assert clipped_labels(win) == []

    games = [LAST_EPOCH, Game("Path of Exile 2", ("steam_app_2694490",))]
    dlg = GameDialog(games, taken={"Last Epoch"})
    qtbot.addWidget(dlg)
    dlg.show()
    dlg.games.setCurrentRow(0)
    dlg._accept_if_valid()  # shows the "already exists" error under the list
    QApplication.processEvents()
    assert clipped_labels(dlg) == []

    for mode in MODES:
        mapping = MappingDialog(e.BTN_SIDE, Action((e.KEY_1,), mode, 2))
        qtbot.addWidget(mapping)
        mapping.show()
        mapping.keys.setText("Ctrl+Banana")  # error label appears too
        QApplication.processEvents()
        assert clipped_labels(mapping) == [], mode


def test_language_picker_shows_a_flag_for_every_language(window):
    for index in range(window.language.count()):
        code = window.language.itemData(index)
        icon = window.language.itemIcon(index)
        if code == i18n.AUTO:
            continue
        assert not icon.isNull(), code
        assert not icon.pixmap(QSize(20, 15), 1.5).isNull(), code


def test_logo_is_a_valid_svg_and_is_the_window_icon(window):
    from PySide6.QtSvg import QSvgRenderer

    from linmbc.gui.main_window import LOGO

    assert QSvgRenderer(str(LOGO)).isValid()
    assert not window.windowIcon().isNull()
    assert not window.windowIcon().pixmap(QSize(32, 32), 1.5).isNull()
