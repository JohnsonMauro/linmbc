"""Pick the game (or any application) a new profile is for."""

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


class GameDialog(QDialog):
    def __init__(self, games: list[Game], taken: set[str], parent: QWidget | None = None) -> None:
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
    def _accept_if_valid(self) -> None:
        game = self.chosen()
        if game is None:
            return
        if game.name.lower() in self._taken:
            self.error.setText(tr("game.exists", name=game.name))
            return
        self.accept()
