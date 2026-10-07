"""Mouse icons with the configured button highlighted, drawn in the theme's colours.

Breeze ships left/middle/right click icons but none for the side buttons, so
all of them are drawn here in one style. Geometry is on a 24x24 grid (top of
the mouse = where the cable is; the user's thumb rests on the left side).
"""

from evdev import ecodes as e
from PySide6.QtCore import QPointF, QRect, QRectF, QSize, Qt
from PySide6.QtGui import (
    QColor,
    QIcon,
    QIconEngine,
    QPainter,
    QPainterPath,
    QPalette,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import QApplication

GRID = 24.0
BODY = QRectF(7, 2, 11, 20)  # x, y, w, h
SPLIT_Y = 10.0
MID_X = BODY.center().x()
WHEEL = QRectF(MID_X - 1.5, 3.8, 3, 4.4)
SIDE_FRONT = QRectF(4.2, 9.5, 2.3, 3.2)
SIDE_REAR = QRectF(4.2, 13.5, 2.3, 3.2)
RIGHT_UPPER = QRectF(18.5, 9.5, 2.3, 3.2)
RIGHT_LOWER = QRectF(18.5, 13.5, 2.3, 3.2)
TASK_DOT = QRectF(MID_X - 1.2, 11.5, 2.4, 2.4)

# A point inside each button's area, used by the tests to check what is lit.
HIGHLIGHT_SPOTS = {
    e.BTN_LEFT: (9.5, 6.5),
    e.BTN_RIGHT: (15.5, 6.5),
    e.BTN_MIDDLE: WHEEL.center().toTuple(),
    e.BTN_SIDE: SIDE_REAR.center().toTuple(),
    e.BTN_EXTRA: SIDE_FRONT.center().toTuple(),
    e.BTN_FORWARD: RIGHT_UPPER.center().toTuple(),
    e.BTN_BACK: RIGHT_LOWER.center().toTuple(),
    e.BTN_TASK: TASK_DOT.center().toTuple(),
}


def _body() -> QPainterPath:
    path = QPainterPath()
    path.addRoundedRect(BODY, 5.5, 5.5)
    return path


def _half(left: bool) -> QPainterPath:
    x = BODY.left() if left else MID_X
    clip = QPainterPath()
    clip.addRect(QRectF(x, BODY.top(), BODY.width() / 2, SPLIT_Y - BODY.top()))
    return _body().intersected(clip).subtracted(_rounded(WHEEL))


def _rounded(rect: QRectF, radius: float = 0.8) -> QPainterPath:
    path = QPainterPath()
    path.addRoundedRect(rect, radius, radius)
    return path


def _area(code: int) -> QPainterPath | None:
    shapes = {
        e.BTN_LEFT: lambda: _half(left=True),
        e.BTN_RIGHT: lambda: _half(left=False),
        e.BTN_MIDDLE: lambda: _rounded(WHEEL),
        e.BTN_SIDE: lambda: _rounded(SIDE_REAR),
        e.BTN_EXTRA: lambda: _rounded(SIDE_FRONT),
        e.BTN_FORWARD: lambda: _rounded(RIGHT_UPPER),
        e.BTN_BACK: lambda: _rounded(RIGHT_LOWER),
        e.BTN_TASK: lambda: _rounded(TASK_DOT, 1.2),
    }
    make = shapes.get(code)
    return make() if make else None


def render_button(
    code: int, size: int, outline: QColor, highlight: QColor, scale: float = 1.0
) -> QPixmap:
    """`size` in logical pixels; drawn natively at `size * scale` device pixels."""
    pixmap = QPixmap(round(size * scale), round(size * scale))
    pixmap.setDevicePixelRatio(scale)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    draw_button(painter, QRectF(0, 0, size, size), code, outline, highlight)
    painter.end()
    return pixmap


def draw_button(
    painter: QPainter, rect: QRectF, code: int, outline: QColor, highlight: QColor
) -> None:
    """Vector drawing into the largest square inside `rect` (sharp at any scale)."""
    side = min(rect.width(), rect.height())
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.translate(rect.center().x() - side / 2, rect.center().y() - side / 2)
    painter.scale(side / GRID, side / GRID)

    area = _area(code)
    if area is not None:
        painter.fillPath(area, highlight)

    pen = QPen(outline, 1.3)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawPath(_body())
    painter.drawLine(QPointF(BODY.left(), SPLIT_Y), QPointF(BODY.right(), SPLIT_Y))
    # the split line stops at the wheel so a lit wheel stays visible
    painter.drawLine(QPointF(MID_X, BODY.top()), QPointF(MID_X, WHEEL.top()))
    painter.drawLine(QPointF(MID_X, WHEEL.bottom()), QPointF(MID_X, SPLIT_Y))
    thin = QPen(outline, 0.9)
    painter.setPen(thin)
    painter.drawPath(_rounded(WHEEL))
    if code in (e.BTN_SIDE, e.BTN_EXTRA):
        painter.drawPath(_rounded(SIDE_FRONT))
        painter.drawPath(_rounded(SIDE_REAR))
    if code in (e.BTN_FORWARD, e.BTN_BACK):
        painter.drawPath(_rounded(RIGHT_UPPER))
        painter.drawPath(_rounded(RIGHT_LOWER))
    painter.restore()


class MouseIconEngine(QIconEngine):
    """Draws the icon at whatever size and screen scale Qt asks for, so a 4K screen
    at 150 % gets real pixels instead of a small bitmap stretched (blurry, distorted)."""

    def __init__(self, code: int) -> None:
        super().__init__()
        self.code = code

    def _colors(self) -> tuple[QColor, QColor]:
        palette = QApplication.palette()
        return (
            palette.color(QPalette.ColorRole.WindowText),
            palette.color(QPalette.ColorRole.Highlight),
        )

    def paint(self, painter: QPainter, rect: QRect, _mode, _state) -> None:
        draw_button(painter, QRectF(rect), self.code, *self._colors())

    def pixmap(self, size: QSize, mode, state) -> QPixmap:
        return self.scaledPixmap(size, mode, state, 1.0)

    def scaledPixmap(self, size: QSize, _mode, _state, scale: float) -> QPixmap:
        side = min(size.width(), size.height())
        return render_button(self.code, side, *self._colors(), scale=scale)

    def clone(self) -> "MouseIconEngine":
        return MouseIconEngine(self.code)


def button_icon(code: int, _size: int = 32) -> QIcon:
    """Icon for `code` in the current palette (works in light and dark themes)."""
    return QIcon(MouseIconEngine(code))
