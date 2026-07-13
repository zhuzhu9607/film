import os
import sys
from pathlib import Path

os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")

from PySide6.QtCore import QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication
from filmcut.main_window import MainWindow
from filmcut.detector import detect_frames
from filmcut.image_io import load_image, make_preview


def main():
    if "--smoke-image" in sys.argv:
        index = sys.argv.index("--smoke-image")
        target = Path(sys.argv[index + 1])
        paths = sorted(target.glob("*.tif")) if target.is_dir() else [target]
        for path in paths:
            image = load_image(path)
            boxes = detect_frames(make_preview(image))
            if not boxes:
                return 2
        return 0
    app = QApplication(sys.argv)
    app.setApplicationName("胶片分格")
    app.setOrganizationName("Local")
    icon_name = "filmstrip.icns" if sys.platform == "darwin" else "filmstrip.ico"
    icon_path = Path(getattr(sys, "_MEIPASS", Path(__file__).parent)) / "assets" / icon_name
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))
    window = MainWindow()
    window.show()
    if "--smoke-test" in sys.argv:
        QTimer.singleShot(800, app.quit)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
