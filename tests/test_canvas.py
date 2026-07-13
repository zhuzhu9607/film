import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np

from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QImage, QMouseEvent, QWheelEvent
from PySide6.QtWidgets import QApplication

from filmcut.canvas import CropCanvas
from filmcut.main_window import MainWindow, NumericSlider


app = QApplication.instance() or QApplication([])
canvas = CropCanvas()
canvas.resize(900, 600)
canvas.set_image(QImage(500, 1800, QImage.Format_RGB888))
before = canvas._image_rect()
event = QWheelEvent(QPointF(450, 300), QPointF(450, 300), QPoint(), QPoint(0, 120),
                    Qt.NoButton, Qt.NoModifier, Qt.ScrollUpdate, False)
canvas.wheelEvent(event)
after = canvas._image_rect()
assert canvas.zoom > 1
assert after.width() > before.width()
press = QMouseEvent(QEvent.MouseButtonPress, QPointF(450, 300), QPointF(450, 300),
                    Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
canvas.mousePressEvent(press)
assert canvas._panning
move = QMouseEvent(QEvent.MouseMove, QPointF(450, 250), QPointF(450, 250),
                   Qt.NoButton, Qt.LeftButton, Qt.NoModifier)
canvas.mouseMoveEvent(move)
release = QMouseEvent(QEvent.MouseButtonRelease, QPointF(450, 250), QPointF(450, 250),
                      Qt.LeftButton, Qt.NoButton, Qt.NoModifier)
canvas.mouseReleaseEvent(release)
assert not canvas._panning
assert abs(canvas.pan.y()) > 1

canvas.set_boxes([(.1, .1, .9, .3)])
canvas.zoom = 1.0
small_delete = canvas._delete_button_rect(canvas._to_screen(canvas.boxes[0])).width()
canvas.zoom = 4.0
large_delete = canvas._delete_button_rect(canvas._to_screen(canvas.boxes[0])).width()
assert large_delete > small_delete
canvas.zoom = 1.0
delete_pos = canvas._delete_button_rect(canvas._to_screen(canvas.boxes[0])).center()
delete_event = QMouseEvent(QEvent.MouseButtonPress, delete_pos, delete_pos,
                           Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
canvas.mousePressEvent(delete_event)
assert len(canvas.boxes) == 0
blank_pos = canvas._image_rect().center()
canvas._track_blank_hover(blank_pos)
canvas._show_hover_hint()
assert canvas._hover_hint
canvas._track_blank_hover(blank_pos + QPointF(3, 0))
assert not canvas._hover_hint

canvas.set_boxes([(.1, .1, .9, .3)])
canvas.zoom = 2.0
canvas.pan = QPointF(12, 18)
canvas.replace_image(QImage(500, 1800, QImage.Format_RGB888))
assert len(canvas.boxes) == 1
assert canvas.zoom == 2.0
assert canvas.pan == QPointF(12, 18)

centered = NumericSlider(-30, 30, 0, "%")
assert centered.value() == 0
left = NumericSlider(0, 40, 0, special="自动")
assert left.label.text() == "自动"
right = NumericSlider(85, 100, 98)
assert right.value() == 98
window = MainWindow()
assert window.preset.currentText() == "标准"
assert window.expand_x.value() == 0
assert window.expand_y.value() == 0
assert window.negative_toggle.isCheckable()
window.preview = np.full((2, 2, 3), 10, np.uint8)
window.canvas.set_image(window._preview_qimage())
window.negative_toggle.click()
assert window.canvas.image.pixelColor(0, 0).red() == 245
window.negative_toggle.click()
assert window.canvas.image.pixelColor(0, 0).red() == 10
print("canvas and slider tests: PASS")
