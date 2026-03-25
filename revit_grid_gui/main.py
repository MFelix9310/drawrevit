"""Entry point for the Revit Grid Generator GUI."""

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from ui.main_window import MainWindow


def load_stylesheet() -> str:
    qss_path = Path(__file__).parent / "styles" / "dark_theme.qss"
    if qss_path.exists():
        return qss_path.read_text(encoding="utf-8")
    return ""


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Revit Grid Generator")
    app.setStyleSheet(load_stylesheet())

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
