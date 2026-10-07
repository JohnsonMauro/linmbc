"""Profile list: Default pinned on top, game profiles draggable, red trash per profile."""

from PySide6.QtCore import QSize, Qt, QTimer, Signal, Slot
from PySide6.QtGui import QColor, QDropEvent, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QToolButton,
    QWidget,
)

from linmbc.i18n import tr

TRASH_RED = QColor("#da4453")  # Breeze "negative" red
ICON_SIZE = 16


def red_trash_icon() -> QIcon | None:
    """The theme's trash icon tinted red; None when the theme has no such icon."""
    base = QIcon.fromTheme("edit-delete")
    if base.isNull():
        return None
    pixmap = base.pixmap(ICON_SIZE, ICON_SIZE)
    tinted = QPixmap(pixmap.size())
    tinted.setDevicePixelRatio(pixmap.devicePixelRatio())
    tinted.fill(Qt.GlobalColor.transparent)
    painter = QPainter(tinted)
    painter.drawPixmap(0, 0, pixmap)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
    painter.fillRect(tinted.rect(), TRASH_RED)
    painter.end()
    return QIcon(tinted)


class _Row(QWidget):
    def __init__(self, text: str, removable: bool, on_remove) -> None:
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 2, 2, 2)
        self.label = QLabel(text)
        self.label.setToolTip(text)  # full name if the column is too narrow
        layout.addWidget(self.label, 1)
        self.trash: QToolButton | None = None
        if removable:
            self.trash = QToolButton()
            icon = red_trash_icon()
            if icon is None:
                self.trash.setText("✕")
                self.trash.setStyleSheet(f"color: {TRASH_RED.name()}; font-weight: bold;")
            else:
                self.trash.setIcon(icon)
                self.trash.setIconSize(QSize(ICON_SIZE, ICON_SIZE))
            self.trash.setAutoRaise(True)
            self.trash.setToolTip(tr("profiles.remove"))
            self.trash.clicked.connect(on_remove)
            layout.addWidget(self.trash)

    def set_bold(self, bold: bool) -> None:
        font = self.label.font()
        font.setBold(bold)
        self.label.setFont(font)


class ProfileList(QListWidget):
    """Emits names only; the window owns the files and the saved order."""

    remove_requested = Signal(str)
    order_changed = Signal(list)  # game profile names in their new order

    def __init__(self, pinned: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.pinned = pinned
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setToolTip(tr("profiles.drag_hint"))
        self._last_order: list[str] = []
        # Either signal may announce a drag; duplicates are dropped by _moved.
        self.model().rowsMoved.connect(self._moved)

    def fill(self, names: list[str], labels: dict[str, str], select: str | None) -> None:
        """`names` = game profiles in display order; the pinned profile always goes first."""
        self.blockSignals(True)
        self.clear()
        for name in [self.pinned, *names]:
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, name)
            if name == self.pinned:
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsDragEnabled)
            self.addItem(item)
            row = _Row(
                labels.get(name, name),
                removable=name != self.pinned,
                on_remove=lambda _=False, n=name: self.remove_requested.emit(n),
            )
            item.setSizeHint(row.sizeHint())
            self.setItemWidget(item, row)
            if name == select:
                self.setCurrentItem(item)
        if self.currentItem() is None:
            self.setCurrentRow(0)
        self._last_order = list(names)
        self.blockSignals(False)

    def names(self) -> list[str]:
        return [self.item(r).data(Qt.ItemDataRole.UserRole) for r in range(self.count())]

    def selected_name(self) -> str | None:
        item = self.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def mark_active(self, active: str) -> None:
        for row in range(self.count()):
            item = self.item(row)
            widget = self.itemWidget(item)
            if isinstance(widget, _Row):
                widget.set_bold(item.data(Qt.ItemDataRole.UserRole) == active)

    def row_widget(self, name: str) -> _Row | None:
        for row in range(self.count()):
            item = self.item(row)
            if item.data(Qt.ItemDataRole.UserRole) == name:
                widget = self.itemWidget(item)
                return widget if isinstance(widget, _Row) else None
        return None

    def dropEvent(self, event: QDropEvent) -> None:
        super().dropEvent(event)
        QTimer.singleShot(0, self._moved)  # after Qt has finished moving the item

    @Slot()
    def _moved(self, *_args) -> None:
        order = [n for n in self.names() if n != self.pinned]
        if order != self._last_order:
            self._last_order = order
            self.order_changed.emit(order)
