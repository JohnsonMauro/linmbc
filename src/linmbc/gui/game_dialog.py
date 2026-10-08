"""Pick the game (or any application) a new profile is for."""

from collections.abc import Sequence
from dataclasses import dataclass

from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from linmbc.games import Game
from linmbc.i18n import tr

OWN_CLASS = "linmbc"  # this GUI's app id (gui/app.py)
# Classes many windows share, so the title is what tells them apart:
# Lutris/umu games without a umu id all get steam_app_default.
SHARED_CLASSES = frozenset({"steam_app_default"})


@dataclass(frozen=True)
class SeenWindow:
    """A window that had focus since the daemon started."""

    window_class: str
    resource_name: str
    title: str

    @property
    def label(self) -> str:
        return " — ".join(part for part in (self.title, self.window_class) if part)

    def as_game(self) -> Game:
        use_title = bool(self.title) and self.window_class.lower() in SHARED_CLASSES
        return Game(
            self.title or self.window_class, (self.title if use_title else self.window_class,)
        )


class GameDialog(QDialog):
    def __init__(
        self,
        games: list[Game],
        taken: set[str],
        parent: QWidget | None = None,
        seen: Sequence[SeenWindow] = (),
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("game.title"))
        self.setMinimumWidth(440)
        self._taken = {name.lower() for name in taken}

        self.from_list = QRadioButton(tr("game.installed"))
        self.games = QListWidget()
        for game in games:
            item = QListWidgetItem(game.name)
            item.setData(Qt.ItemDataRole.UserRole, game)
            if game.name.lower() in self._taken:
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEnabled)
            self.games.addItem(item)
        if not games:
            self.games.addItem(tr("game.none_found"))
            self.games.setEnabled(False)
        self.games.currentItemChanged.connect(lambda *_: self.from_list.setChecked(True))
        self.games.itemDoubleClicked.connect(lambda *_: self._accept_if_valid())

        self.other = QRadioButton(tr("game.other"))
        self.seen_label = QLabel(tr("game.seen"))
        self.seen_label.setWordWrap(True)
        self.seen = QListWidget()
        for window in seen:
            if window.window_class.lower() == OWN_CLASS:
                continue
            item = QListWidgetItem(window.label)
            item.setData(Qt.ItemDataRole.UserRole, window)
            self.seen.addItem(item)
        self.seen.currentItemChanged.connect(self._fill_from_seen)
        self.seen_label.setHidden(self.seen.count() == 0)
        self.seen.setHidden(self.seen.count() == 0)
        self.name = QLineEdit()
        self.window = QLineEdit()
        hint = QLabel(tr("game.window_hint"))
        hint.setWordWrap(True)
        for edit in (self.name, self.window):
            edit.textEdited.connect(lambda *_: self.other.setChecked(True))
        other_form = QFormLayout()
        other_form.addRow(tr("game.name"), self.name)
        other_form.addRow(tr("game.window"), self.window)
        other_form.addRow("", hint)

        self.error = QLabel()
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.accepted.connect(self._accept_if_valid)
        self.buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(self.from_list)
        layout.addWidget(self.games)
        layout.addWidget(self.other)
        layout.addWidget(self.seen_label)
        layout.addWidget(self.seen)
        layout.addLayout(other_form)
        layout.addWidget(self.error)
        layout.addWidget(self.buttons)
        (self.from_list if games else self.other).setChecked(True)

    def chosen(self) -> Game | None:
        if self.from_list.isChecked():
            item = self.games.currentItem()
            game = item.data(Qt.ItemDataRole.UserRole) if item else None
            return game if isinstance(game, Game) else None
        name, window = self.name.text().strip(), self.window.text().strip()
        if not name or not window:
            return None
        return Game(name, tuple(w.strip() for w in window.split(",") if w.strip()))

    @Slot()
    def _fill_from_seen(self) -> None:
        item = self.seen.currentItem()
        window = item.data(Qt.ItemDataRole.UserRole) if item else None
        if not isinstance(window, SeenWindow):
            return
        game = window.as_game()
        self.name.setText(game.name)
        self.window.setText(", ".join(game.match))
        self.other.setChecked(True)

    @Slot()
    def _accept_if_valid(self) -> None:
        game = self.chosen()
        if game is None:
            return
        if game.name.lower() in self._taken:
            self.error.setText(tr("game.exists", name=game.name))
            return
        self.accept()
