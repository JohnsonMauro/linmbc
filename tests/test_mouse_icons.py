import pytest

pytest.importorskip("PySide6")

from evdev import ecodes as e  # noqa: E402
from PySide6.QtGui import QColor  # noqa: E402

from linmbc.gui.mouse_icons import HIGHLIGHT_SPOTS, render_button  # noqa: E402

HIGHLIGHT = QColor("#3daee9")
OUTLINE = QColor("#fcfcfc")
SIZE = 48


def lit(image, spot):
    """Is the unit-coordinate spot painted with the highlight colour?"""
    x, y = (round(c * SIZE / 24) for c in spot)
    return image.pixelColor(x, y).name() == HIGHLIGHT.name()


@pytest.mark.usefixtures("qapp")
@pytest.mark.parametrize("code", list(HIGHLIGHT_SPOTS))
def test_each_button_lights_only_its_own_spot(code):
    image = render_button(code, SIZE, OUTLINE, HIGHLIGHT).toImage()
    for other, spot in HIGHLIGHT_SPOTS.items():
        assert lit(image, spot) is (other == code), (code, other)


@pytest.mark.usefixtures("qapp")
def test_side_buttons_are_on_the_left_side_front_above_rear():
    front = HIGHLIGHT_SPOTS[e.BTN_EXTRA]
    rear = HIGHLIGHT_SPOTS[e.BTN_SIDE]
    assert front[0] < 8 and rear[0] < 8  # left of the body
    assert front[1] < rear[1]  # front button is nearer the cable/top


@pytest.mark.usefixtures("qapp")
@pytest.mark.parametrize("scale", [1.0, 1.5, 2.0])
def test_icon_is_drawn_at_the_screen_scale_not_stretched(scale):
    from PySide6.QtCore import QSize

    from linmbc.gui.mouse_icons import button_icon

    pixmap = button_icon(e.BTN_LEFT).pixmap(QSize(32, 32), scale)
    assert pixmap.width() == round(32 * scale)  # real pixels, not a 32 px image upscaled
    assert pixmap.devicePixelRatio() == scale
    # drawn natively at that size: the lit spot is exactly the highlight colour
    image = pixmap.toImage()
    x, y = (round(c * pixmap.width() / 24) for c in HIGHLIGHT_SPOTS[e.BTN_LEFT])
    from PySide6.QtGui import QPalette
    from PySide6.QtWidgets import QApplication

    expected = QApplication.palette().color(QPalette.ColorRole.Highlight).name()
    assert image.pixelColor(x, y).name() == expected
