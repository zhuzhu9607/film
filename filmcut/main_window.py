from __future__ import annotations

from pathlib import Path
import traceback

import numpy as np
from PySide6.QtCore import QObject, QSettings, QThread, Qt, Signal, Slot
from PySide6.QtGui import QImage
from PySide6.QtWidgets import (
    QApplication, QComboBox, QFileDialog, QFormLayout, QFrame, QHBoxLayout, QLabel,
    QLineEdit, QMainWindow, QMessageBox, QProgressBar, QPushButton, QScrollArea,
    QSlider, QStatusBar, QVBoxLayout, QWidget,
)

from .canvas import CropCanvas
from .detector import apply_expansion, detect_frames, expand_normalized
from .image_io import SUPPORTED_EXTENSIONS, invert_image, load_image, make_preview, save_crop


class NumericSlider(QWidget):
    valueChanged = Signal(int)

    def __init__(self, minimum: int, maximum: int, value: int, suffix: str = "", special: str = ""):
        super().__init__()
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(minimum, maximum)
        self.label = QLabel()
        self.label.setFixedWidth(48)
        self.label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.suffix = suffix
        self.special = special
        self.slider.valueChanged.connect(self._changed)
        row.addWidget(self.slider, 1)
        row.addWidget(self.label)
        self.setValue(value)

    def _changed(self, value: int):
        self.label.setText(self.special if self.special and value == self.slider.minimum() else f"{value}{self.suffix}")
        self.valueChanged.emit(value)

    def value(self) -> int:
        return self.slider.value()

    def setValue(self, value: int):
        self.slider.setValue(value)
        self._changed(self.slider.value())

    def blockSignals(self, block: bool):
        self.slider.blockSignals(block)
        return super().blockSignals(block)


class ExportWorker(QObject):
    progress = Signal(int, str)
    finished = Signal(int, str)
    failed = Signal(str)

    def __init__(self, image, boxes, out_dir, stem, fmt, quality, depth, x_expand, y_expand,
                 invert_negative=False):
        super().__init__()
        self.image = image
        self.boxes = boxes
        self.out_dir = Path(out_dir)
        self.stem = stem
        self.fmt = fmt
        self.quality = quality
        self.depth = depth
        self.x_expand = x_expand
        self.y_expand = y_expand
        self.invert_negative = invert_negative

    @Slot()
    def run(self):
        try:
            count = 0
            suffix = ".tif" if self.fmt == "TIFF" else ".jpg"
            digits = max(2, len(str(len(self.boxes))))
            for i, box in enumerate(self.boxes, 1):
                x1, y1, x2, y2 = apply_expansion(
                    box, self.x_expand, self.y_expand, self.image.shape[:2]
                )
                if x2 <= x1 or y2 <= y1:
                    continue
                output = self.out_dir / f"{self.stem}_{i:0{digits}d}{suffix}"
                crop = self.image[y1:y2, x1:x2]
                if self.invert_negative:
                    crop = invert_image(crop)
                save_crop(output, crop, self.fmt, self.quality, self.depth)
                count += 1
                self.progress.emit(round(i / len(self.boxes) * 100), output.name)
            self.finished.emit(count, str(self.out_dir))
        except Exception:
            self.failed.emit(traceback.format_exc())


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("胶片分格 · FilmStrip Cutter")
        self.resize(1380, 860)
        self.setAcceptDrops(True)
        self.image: np.ndarray | None = None
        self.preview: np.ndarray | None = None
        self.source_path: Path | None = None
        self.export_thread: QThread | None = None
        self.settings = QSettings("Local", "FilmStripCutter")
        self._build_ui()
        self._style()

    def _build_ui(self):
        root = QWidget()
        layout = QHBoxLayout(root)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(16)
        self.canvas = CropCanvas()
        self.canvas.selectionChanged.connect(self._selection_label)
        layout.addWidget(self.canvas, 1)

        side_scroll = QScrollArea()
        side_scroll.setWidgetResizable(True)
        side_scroll.setFixedWidth(332)
        side_scroll.setFrameShape(QFrame.NoFrame)
        side = QWidget()
        side_layout = QVBoxLayout(side)
        side_layout.setContentsMargins(12, 2, 12, 2)
        side_layout.setSpacing(0)
        side_layout.addWidget(self._source_panel())
        side_layout.addWidget(self._detect_panel())
        side_layout.addWidget(self._crop_panel())
        side_layout.addWidget(self._export_panel())
        side_layout.addStretch()
        side_scroll.setWidget(side)
        layout.addWidget(side_scroll)
        self.setCentralWidget(root)

        status = QStatusBar()
        self.status_text = QLabel("准备好 · 可直接拖入图片")
        self.progress = QProgressBar()
        self.progress.setFixedWidth(180)
        self.progress.setVisible(False)
        status.addWidget(self.status_text, 1)
        status.addPermanentWidget(self.progress)
        self.setStatusBar(status)

    def _panel(self, title: str):
        frame = QFrame()
        frame.setObjectName("panel")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(4, 16, 4, 16)
        layout.setSpacing(10)
        heading = QLabel(title)
        heading.setObjectName("heading")
        layout.addWidget(heading)
        return frame, layout

    def _source_panel(self):
        frame, layout = self._panel("扫描文件")
        self.file_label = QLabel("尚未打开文件")
        self.file_label.setWordWrap(True)
        self.file_label.setObjectName("muted")
        layout.addWidget(self.file_label)
        button = QPushButton("选择 TIF / RAW / 图片")
        button.clicked.connect(self.open_file)
        layout.addWidget(button)
        self.negative_toggle = QPushButton("一键反色")
        self.negative_toggle.setObjectName("negativeToggle")
        self.negative_toggle.setCheckable(True)
        self.negative_toggle.setToolTip("负片模式：预览和导出都会反色，不修改源文件")
        self.negative_toggle.toggled.connect(self._toggle_negative)
        layout.addWidget(self.negative_toggle)
        return frame

    def _detect_panel(self):
        frame, layout = self._panel("自动分格")
        form = QFormLayout()
        self.expected = NumericSlider(0, 40, 0, special="自动")
        form.addRow("总张数", self.expected)
        layout.addLayout(form)
        self.frame_count = QLabel("0 个裁剪框")
        self.frame_count.setObjectName("accent")
        layout.addWidget(self.frame_count)
        self.canvas.boxesChanged.connect(self._boxes_changed)
        return frame

    def _crop_panel(self):
        frame, layout = self._panel("黑边与齿孔")
        self.preset = QComboBox()
        self.preset.addItems(["标准", "纯照片", "少量黑边", "完整齿孔", "自定义"])
        self.preset.currentTextChanged.connect(self._apply_preset)
        form = QFormLayout()
        self.expand_x = NumericSlider(-30, 30, 0, suffix="%")
        self.expand_y = NumericSlider(-30, 30, 0, suffix="%")
        self.expand_x.valueChanged.connect(self._customized)
        self.expand_y.valueChanged.connect(self._customized)
        form.addRow("裁剪风格", self.preset)
        form.addRow("左右扩展", self.expand_x)
        form.addRow("上下扩展", self.expand_y)
        layout.addLayout(form)
        button = QPushButton("按以上参数自动识别画格")
        button.setObjectName("primary")
        button.clicked.connect(self.auto_detect)
        layout.addWidget(button)
        self._apply_preset("标准")
        return frame

    def _export_panel(self):
        frame, layout = self._panel("高质量导出")
        form = QFormLayout()
        self.output_format = QComboBox(); self.output_format.addItems(["TIFF", "JPG"])
        self.output_format.currentTextChanged.connect(self._format_changed)
        self.tiff_depth = QComboBox(); self.tiff_depth.addItems(["原始位深", "16 位", "8 位"])
        self.jpg_quality = NumericSlider(85, 100, 98)
        self.name_edit = QLineEdit("film")
        self.output_edit = QLineEdit()
        self.output_edit.setPlaceholderText("选择导出文件夹")
        form.addRow("文件格式", self.output_format)
        form.addRow("TIFF 位深", self.tiff_depth)
        form.addRow("JPG 质量", self.jpg_quality)
        form.addRow("文件名前缀", self.name_edit)
        directory_row = QWidget()
        directory_row.setObjectName("directoryRow")
        directory_layout = QHBoxLayout(directory_row)
        directory_layout.setContentsMargins(0, 0, 0, 0)
        directory_layout.setSpacing(4)
        directory_layout.addWidget(self.output_edit, 1)
        browse = QPushButton("…")
        browse.setObjectName("browse")
        browse.setFixedWidth(34)
        browse.clicked.connect(self.choose_output)
        directory_layout.addWidget(browse)
        form.addRow("导出目录", directory_row)
        layout.addLayout(form)
        self.export_button = QPushButton("导出全部裁剪框")
        self.export_button.setObjectName("primary")
        self.export_button.clicked.connect(self.export_all)
        layout.addWidget(self.export_button)
        self._format_changed("TIFF")
        return frame

    def _style(self):
        self.setStyleSheet("""
            QMainWindow, QWidget { background: #111214; color: #e7e7e8; font-family: 'Microsoft YaHei UI'; font-size: 13px; }
            NumericSlider, QWidget#directoryRow { background: transparent; }
            QFrame#panel { background: #111214; border: none; border-bottom: 1px solid #292a2e; border-radius: 0; }
            QLabel#heading { font-size: 12px; font-weight: 600; letter-spacing: 1px; color: #a8a9ad; padding: 0 0 2px 0; }
            QLabel#muted { color: #6f7178; font-size: 11px; }
            QLabel#accent { color: #f2a33a; font-size: 12px; font-weight: 600; }
            QPushButton { background: #242529; border: 1px solid #313238; border-radius: 6px; padding: 8px; color: #e4e4e6; }
            QPushButton:hover { background: #2d2e33; border-color: #42434a; }
            QPushButton:pressed { background: #1e1f22; }
            QPushButton#primary { background: #f2a33a; color: #151515; border: none; font-weight: 600; padding: 10px; }
            QPushButton#primary:hover { background: #ffb34f; }
            QPushButton#secondary { background: #1d1e21; }
            QPushButton#browse { padding: 4px; font-size: 15px; background: #202125; }
            QPushButton#negativeToggle:checked { background: #3a2b17; color: #ffc46f; border-color: #8a6030; }
            QPushButton#negativeToggle:checked:hover { background: #46341d; border-color: #a87539; }
            QComboBox, QLineEdit { background: #1a1b1e; border: 1px solid #303136; border-radius: 5px; padding: 6px; min-height: 20px; selection-background-color: #f2a33a; }
            QComboBox:hover, QLineEdit:hover { border-color: #45464d; }
            QComboBox::drop-down { border: none; width: 22px; }
            QScrollArea { background: #111214; border: none; }
            QScrollBar:vertical { background: #111214; width: 8px; margin: 0; }
            QScrollBar::handle:vertical { background: #3a3b40; min-height: 28px; border-radius: 4px; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
            QStatusBar { background: #0d0e10; color: #777980; border-top: 1px solid #24252a; }
            QSlider::groove:horizontal { height: 2px; background: #3a3b40; border-radius: 1px; }
            QSlider::handle:horizontal { background: #f2a33a; width: 12px; margin: -5px 0; border-radius: 6px; }
            QSlider::handle:horizontal:hover { background: #ffb34f; }
            QProgressBar { background: #1a1b1e; border: none; border-radius: 3px; text-align: center; }
            QProgressBar::chunk { background: #f2a33a; border-radius: 3px; }
        """)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        paths = [Path(u.toLocalFile()) for u in event.mimeData().urls()]
        valid = next((p for p in paths if p.suffix.lower() in SUPPORTED_EXTENSIONS), None)
        if valid:
            self.load_path(valid)

    def open_file(self):
        raw = " ".join(f"*{x}" for x in sorted(SUPPORTED_EXTENSIONS))
        path, _ = QFileDialog.getOpenFileName(self, "打开胶片扫描图", str(self.settings.value("lastOpen", "")),
                                               f"支持的图片 ({raw});;所有文件 (*.*)")
        if path:
            self.load_path(Path(path))

    def load_path(self, path: Path):
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            self.status_text.setText("正在读取原始图像…")
            QApplication.processEvents()
            image = load_image(path)
            preview = make_preview(image)
            h, w = image.shape[:2]
            self.image, self.preview, self.source_path = image, preview, path
            self.canvas.set_image(self._preview_qimage())
            self.file_label.setText(f"{path.name}\n{w:,} × {h:,} px · {image.dtype}")
            self.name_edit.setText(path.stem)
            default_out = path.parent / f"{path.stem}_分格"
            self.output_edit.setText(str(default_out))
            self.settings.setValue("lastOpen", str(path.parent))
            self.auto_detect()
            self.status_text.setText(f"已载入 {path.name}")
        except Exception as exc:
            QMessageBox.critical(self, "无法打开", f"{path.name}\n\n{exc}")
            self.status_text.setText("打开失败")
        finally:
            QApplication.restoreOverrideCursor()

    def auto_detect(self):
        if self.preview is None:
            return
        boxes = detect_frames(self.preview, expected_count=self.expected.value())
        boxes = [expand_normalized(b, self.expand_x.value(), self.expand_y.value()) for b in boxes]
        self.canvas.set_boxes(boxes)
        self._boxes_changed()
        self.status_text.setText(f"自动识别完成：{len(boxes)} 格")

    def _preview_qimage(self) -> QImage:
        preview = invert_image(self.preview) if self.negative_toggle.isChecked() else self.preview
        return QImage(preview.data, preview.shape[1], preview.shape[0], preview.strides[0],
                      QImage.Format_RGB888).copy()

    def _toggle_negative(self, checked: bool):
        self.negative_toggle.setText("已反色 · 点击还原" if checked else "一键反色")
        if self.preview is not None:
            self.canvas.replace_image(self._preview_qimage())
            self.status_text.setText("负片反色已开启，预览和导出均已反色" if checked else "已恢复原始色彩")

    def _boxes_changed(self):
        self.frame_count.setText(f"{len(self.canvas.boxes)} 个裁剪框")

    def _selection_label(self, index: int):
        if index >= 0:
            self.status_text.setText(f"已选择第 {index + 1} 格")

    def _apply_preset(self, text: str):
        values = {"标准": (0, 0), "纯照片": (-2, -4), "少量黑边": (2, 4), "完整齿孔": (3, 20)}
        if text in values:
            self.expand_x.blockSignals(True); self.expand_y.blockSignals(True)
            self.expand_x.setValue(values[text][0]); self.expand_y.setValue(values[text][1])
            self.expand_x.blockSignals(False); self.expand_y.blockSignals(False)
            if self.image is not None:
                self.status_text.setText("裁剪风格已改变，请点击“按以上参数自动识别画格”刷新")

    def _customized(self):
        if self.preset.currentText() != "自定义":
            self.preset.blockSignals(True); self.preset.setCurrentText("自定义"); self.preset.blockSignals(False)
        if self.image is not None:
            self.status_text.setText("裁剪参数已改变，请点击“按以上参数自动识别画格”刷新")

    def _format_changed(self, fmt: str):
        self.tiff_depth.setEnabled(fmt == "TIFF")
        self.jpg_quality.setEnabled(fmt == "JPG")

    def choose_output(self):
        path = QFileDialog.getExistingDirectory(self, "选择导出目录", self.output_edit.text())
        if path:
            self.output_edit.setText(path)

    def export_all(self):
        if self.image is None or not self.canvas.boxes:
            QMessageBox.information(self, "还不能导出", "请先打开图片并保留至少一个裁剪框。")
            return
        out_dir = self.output_edit.text().strip()
        if not out_dir:
            self.choose_output(); out_dir = self.output_edit.text().strip()
        if not out_dir:
            return
        stem = self.name_edit.text().strip() or "film"
        invalid = '<>:"/\\|?*'
        stem = "".join("_" if c in invalid else c for c in stem)
        self.export_button.setEnabled(False)
        self.progress.setValue(0); self.progress.setVisible(True)
        self.export_thread = QThread(self)
        self.worker = ExportWorker(self.image, list(self.canvas.boxes), out_dir, stem,
                                   self.output_format.currentText(), self.jpg_quality.value(),
                                   self.tiff_depth.currentText(), 0, 0,
                                   self.negative_toggle.isChecked())
        self.worker.moveToThread(self.export_thread)
        self.export_thread.started.connect(self.worker.run)
        self.worker.progress.connect(self._export_progress)
        self.worker.finished.connect(self._export_finished)
        self.worker.failed.connect(self._export_failed)
        self.worker.finished.connect(self.export_thread.quit)
        self.worker.failed.connect(self.export_thread.quit)
        self.export_thread.finished.connect(self.worker.deleteLater)
        self.export_thread.finished.connect(self.export_thread.deleteLater)
        self.export_thread.start()

    def _export_progress(self, percent, name):
        self.progress.setValue(percent)
        self.status_text.setText(f"正在导出：{name}")

    def _export_finished(self, count, directory):
        self.export_button.setEnabled(True); self.progress.setVisible(False)
        self.status_text.setText(f"导出完成：{count} 张")
        QMessageBox.information(self, "导出完成", f"已高质量导出 {count} 张照片。\n\n{directory}")

    def _export_failed(self, details):
        self.export_button.setEnabled(True); self.progress.setVisible(False)
        self.status_text.setText("导出失败")
        QMessageBox.critical(self, "导出失败", details[-1800:])
