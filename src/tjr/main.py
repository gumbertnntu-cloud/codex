from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from tjr.core.logging_setup import configure_logging
from tjr.storage.config_store import ConfigStore
from tjr.ui.main_window import MainWindow


def _resolve_icon_path() -> Path | None:
    icon_relative = Path("assets/icons/TJR-icon-1024.png")
    candidates: list[Path] = []
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            candidates.append(Path(meipass) / icon_relative)
    candidates.append(Path(__file__).resolve().parents[2] / icon_relative)
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def run() -> int:
    configure_logging()
    app = QApplication(sys.argv)
    app.setApplicationName("TJR")
    icon_path = _resolve_icon_path()
    if icon_path is not None:
        app.setWindowIcon(QIcon(str(icon_path)))

    config_store = ConfigStore()
    config_store.ensure_exists()
    config = config_store.load()

    window = MainWindow(config_store=config_store, config=config)
    window.show()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(run())
