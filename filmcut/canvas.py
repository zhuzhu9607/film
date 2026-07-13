from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPen
from PySide6.QtWidgets import QWidget


class CropCanvas(QWidget):
    boxesChanged = Signal()
    selectionChanged = Signal(int)

    def __init__(self):
        super().__init__()
        self.setMinimumSize(600, 420)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.image: QImage | None = None
        self.boxes: list[tuple[float, float, float, float]] = []
        self.selected = -1
        self._drag_mode = ""
        self._drag_start = QPointF()
        self._original = None
        self.zoom = 1.0
        self.pan = QPointF()
        self._panning = False
        self._pan_start = QPointF()
        self._pan_original = QPointF()
        self._hover_pos = QPointF()
        self._hover_hint = False
        self._hover_timer = QTimer(self)
        self._hover_timer.setSingleShot(True)
        self._hover_timer.setInterval(850)
        self._hover_timer.timeout.connect(self._show_hover_hint)

    def set_image(self, image: QImage):
        self.image = image
        self.zoom = 1.0
        self.pan = QPointF()
        self.boxes = []
        self.selected = -1
        self._reset_hover()
        self.update()

    def replace_image(self, image: QImage):
        """Replace pixels while preserving crop boxes, zoom and pan."""
        self.image = image
        self.update()

    def set_boxes(self, boxes):
        self.boxes = [tuple(map(float, b)) for b in boxes]
        self.selected = 0 if boxes else -1
        self.selectionChanged.emit(self.selected)
        self.update()

    def _image_rect(self) -> QRectF:
        if not self.image:
            return QRectF()
        margin = 24
        avail = QRectF(margin, margin, self.width() - margin * 2, self.height() - margin * 2)
        scale = min(avail.width() / self.image.width(), avail.height() / self.image.height()) * self.zoom
        size = QPointF(self.image.width() * scale, self.image.height() * scale)
        return QRectF((self.width() - size.x()) / 2 + self.pan.x(),
                      (self.height() - size.y()) / 2 + self.pan.y(), size.x(), size.y())

    def _clamp_pan(self):
        if not self.image or self.zoom <= 1.001:
            self.pan = QPointF()
            return
        rect = self._image_rect()
        px, py = self.pan.x(), self.pan.y()
        if rect.width() >= self.width():
            px += min(0.0, -rect.left()) if rect.left() > 0 else max(0.0, self.width() - rect.right())
        else:
            px = 0.0
        if rect.height() >= self.height():
            py += min(0.0, -rect.top()) if rect.top() > 0 else max(0.0, self.height() - rect.bottom())
        else:
            py = 0.0
        self.pan = QPointF(px, py)

    def _to_screen(self, box) -> QRectF:
        r = self._image_rect()
        x1, y1, x2, y2 = box
        return QRectF(r.x() + x1 * r.width(), r.y() + y1 * r.height(),
                      (x2 - x1) * r.width(), (y2 - y1) * r.height())

    def _to_norm(self, p: QPointF) -> QPointF:
        r = self._image_rect()
        return QPointF((p.x() - r.x()) / r.width(), (p.y() - r.y()) / r.height())

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#111318"))
        if not self.image:
            painter.setPen(QColor("#777e8c"))
            painter.drawText(self.rect(), Qt.AlignCenter, "打开图片 · 滚轮缩放 · 空白处拖动平移")
            return
        target = self._image_rect()
        painter.drawImage(target, self.image)
        for i, box in enumerate(self.boxes):
            rect = self._to_screen(box)
            selected = i == self.selected
            painter.setPen(QPen(QColor("#ffb24a" if selected else "#62d6a7"), 3 if selected else 2))
            painter.setBrush(QColor(255, 178, 74, 26) if selected else QColor(98, 214, 167, 18))
            painter.drawRect(rect)
            painter.setBrush(QColor("#ffb24a" if selected else "#62d6a7"))
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(QRectF(rect.x() + 6, rect.y() + 6, 28, 24), 5, 5)
            painter.setPen(QColor("#111318"))
            painter.drawText(QRectF(rect.x() + 6, rect.y() + 6, 28, 24), Qt.AlignCenter, str(i + 1))
            delete_rect = self._delete_button_rect(rect)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor("#e45757"))
            painter.drawRoundedRect(delete_rect, delete_rect.width() * .22, delete_rect.width() * .22)
            painter.setPen(QPen(QColor("#ffffff"), max(1.0, delete_rect.width() * .075)))
            cx = delete_rect.center().x()
            size = delete_rect.width()
            painter.drawLine(QPointF(cx - size * .24, delete_rect.top() + size * .35),
                             QPointF(cx + size * .24, delete_rect.top() + size * .35))
            painter.drawLine(QPointF(cx - size * .13, delete_rect.top() + size * .25),
                             QPointF(cx + size * .13, delete_rect.top() + size * .25))
            painter.drawRoundedRect(QRectF(cx - size * .19, delete_rect.top() + size * .43,
                                           size * .38, size * .31), size * .05, size * .05)
        if self.zoom > 1.01:
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(15, 17, 22, 190))
            painter.drawRoundedRect(QRectF(16, 16, 72, 28), 6, 6)
            painter.setPen(QColor("#e9edf3"))
            painter.drawText(QRectF(16, 16, 72, 28), Qt.AlignCenter, f"{self.zoom:.1f}×")
        if self._hover_hint:
            tip = QRectF(self._hover_pos.x() + 12, self._hover_pos.y() + 14, 132, 30)
            if tip.right() > self.width() - 8: tip.moveRight(self.width() - 8)
            if tip.bottom() > self.height() - 8: tip.moveBottom(self.height() - 8)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(28, 32, 39, 235))
            painter.drawRoundedRect(tip, 7, 7)
            painter.setPen(QColor("#d9dee7"))
            painter.drawText(tip, Qt.AlignCenter, "双击增加裁剪框")

    def _delete_button_rect(self, frame_rect: QRectF) -> QRectF:
        size = max(10.0, min(22.0, min(frame_rect.width(), frame_rect.height()) * .095))
        margin = max(3.0, size * .24)
        return QRectF(frame_rect.right() - size - margin, frame_rect.top() + margin, size, size)

    def _hit_delete(self, pos: QPointF) -> int:
        for i in range(len(self.boxes) - 1, -1, -1):
            if self._delete_button_rect(self._to_screen(self.boxes[i])).adjusted(-3, -3, 3, 3).contains(pos):
                return i
        return -1

    def _reset_hover(self):
        self._hover_timer.stop()
        if self._hover_hint:
            self._hover_hint = False
            self.update()

    def _show_hover_hint(self):
        self._hover_hint = True
        self.update()

    def _track_blank_hover(self, pos: QPointF):
        i, _ = self._hit(pos)
        blank = i < 0 and self._image_rect().contains(pos)
        if not blank:
            self._reset_hover()
            return
        moved = (pos - self._hover_pos).manhattanLength() > 1
        if moved and self._hover_hint:
            self._hover_hint = False
            self.update()
        if moved or (not self._hover_timer.isActive() and not self._hover_hint):
            self._hover_pos = QPointF(pos)
            self._hover_timer.start()

    def _hit(self, pos: QPointF):
        tolerance = 8
        for i in range(len(self.boxes) - 1, -1, -1):
            r = self._to_screen(self.boxes[i])
            if r.adjusted(-tolerance, -tolerance, tolerance, tolerance).contains(pos):
                near_l = abs(pos.x() - r.left()) <= tolerance
                near_r = abs(pos.x() - r.right()) <= tolerance
                near_t = abs(pos.y() - r.top()) <= tolerance
                near_b = abs(pos.y() - r.bottom()) <= tolerance
                mode = ("l" if near_l else "r" if near_r else "") + ("t" if near_t else "b" if near_b else "")
                return i, mode or "move"
        return -1, ""

    def mousePressEvent(self, event):
        if not self.image:
            return
        self._reset_hover()
        if event.button() in (Qt.MiddleButton, Qt.RightButton):
            self._panning = True
            self._pan_start = event.position()
            self._pan_original = QPointF(self.pan)
            self.setCursor(Qt.ClosedHandCursor)
            event.accept()
            return
        if event.button() != Qt.LeftButton:
            return
        delete_index = self._hit_delete(event.position())
        if delete_index >= 0:
            self.boxes.pop(delete_index)
            self.selected = min(delete_index, len(self.boxes) - 1)
            self.selectionChanged.emit(self.selected)
            self.boxesChanged.emit()
            self.update()
            event.accept()
            return
        i, mode = self._hit(event.position())
        self.selected = i
        self.selectionChanged.emit(i)
        if i < 0 and self._image_rect().contains(event.position()):
            self._panning = True
            self._pan_start = event.position()
            self._pan_original = QPointF(self.pan)
            self.setCursor(Qt.ClosedHandCursor)
            event.accept()
            return
        self._drag_mode = mode
        self._drag_start = self._to_norm(event.position())
        self._original = self.boxes[i] if i >= 0 else None
        self.update()

    def mouseMoveEvent(self, event):
        if self._panning:
            delta = event.position() - self._pan_start
            self.pan = self._pan_original + delta
            self._clamp_pan()
            self.update()
            return
        if event.buttons() == Qt.NoButton and not self._drag_mode:
            self._track_blank_hover(event.position())
            return
        if self.selected < 0 or not self._drag_mode or not self._original:
            return
        now = self._to_norm(event.position())
        dx, dy = now.x() - self._drag_start.x(), now.y() - self._drag_start.y()
        x1, y1, x2, y2 = self._original
        if self._drag_mode == "move":
            width, height = x2 - x1, y2 - y1
            x1 = max(0, min(1 - width, x1 + dx)); x2 = x1 + width
            y1 = max(0, min(1 - height, y1 + dy)); y2 = y1 + height
        else:
            if "l" in self._drag_mode: x1 = max(0, min(x2 - .005, x1 + dx))
            if "r" in self._drag_mode: x2 = min(1, max(x1 + .005, x2 + dx))
            if "t" in self._drag_mode: y1 = max(0, min(y2 - .005, y1 + dy))
            if "b" in self._drag_mode: y2 = min(1, max(y1 + .005, y2 + dy))
        self.boxes[self.selected] = (x1, y1, x2, y2)
        self.boxesChanged.emit()
        self.update()

    def mouseReleaseEvent(self, event):
        if self._panning:
            self._panning = False
            self.unsetCursor()
            event.accept()
            return
        self._drag_mode = ""
        self._original = None

    def wheelEvent(self, event):
        if not self.image:
            return
        self._reset_hover()
        delta = event.angleDelta().y()
        if delta == 0:
            delta = event.pixelDelta().y()
        if delta == 0:
            return
        old_rect = self._image_rect()
        pos = event.position()
        u = (pos.x() - old_rect.left()) / max(old_rect.width(), 1)
        v = (pos.y() - old_rect.top()) / max(old_rect.height(), 1)
        factor = 1.18 if delta > 0 else 1 / 1.18
        new_zoom = max(1.0, min(12.0, self.zoom * factor))
        if abs(new_zoom - self.zoom) < .001:
            return
        self.zoom = new_zoom
        centered = self._image_rect()
        desired_left = pos.x() - u * centered.width()
        desired_top = pos.y() - v * centered.height()
        self.pan += QPointF(desired_left - centered.left(), desired_top - centered.top())
        self._clamp_pan()
        self.update()
        event.accept()

    def mouseDoubleClickEvent(self, event):
        if not self.image or not self._image_rect().contains(event.position()):
            return
        self._reset_hover()
        p = self._to_norm(event.position())
        horizontal = self.image.width() >= self.image.height()
        if horizontal:
            box = (max(0, p.x() - .06), .08, min(1, p.x() + .06), .92)
        else:
            box = (.08, max(0, p.y() - .06), .92, min(1, p.y() + .06))
        self.boxes.append(box)
        self.selected = len(self.boxes) - 1
        self.selectionChanged.emit(self.selected)
        self.boxesChanged.emit()
        self.update()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Delete, Qt.Key_Backspace) and self.selected >= 0:
            self.boxes.pop(self.selected)
            self.selected = min(self.selected, len(self.boxes) - 1)
            self.selectionChanged.emit(self.selected)
            self.boxesChanged.emit()
            self.update()
        elif event.key() == Qt.Key_0:
            self.zoom = 1.0; self.pan = QPointF(); self.update()

    def leaveEvent(self, event):
        self._reset_hover()
        super().leaveEvent(event)
