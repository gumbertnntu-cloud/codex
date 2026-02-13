from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from tjr.core.logging_setup import configure_logging
from tjr.storage.config_store import ConfigStore
from tjr.ui.main_window import MainWindow


def run() -> int:
    configure_logging()
    app = QApplication(sys.argv)
    app.setApplicationName("TJR")

    config_store = ConfigStore()
    config_store.ensure_exists()
    config = config_store.load()

    window = MainWindow(config_store=config_store, config=config)
    window.show()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(run())
