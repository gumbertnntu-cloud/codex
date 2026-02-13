from __future__ import annotations

import logging
import time

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from PySide6.QtWidgets import (
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from tjr.core.logging_setup import get_log_path, reset_log_file
from tjr.core.scanner import MatchRecord, ScanProgress, run_scan
from tjr.storage.config_store import AppConfig, ConfigStore
from tjr.ui.results_window import MatchResultsDialog
from tjr.ui.settings_dialog import SettingsDialog
from tjr.ui.smooth_scroll import enable_smooth_wheel_scroll

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    def __init__(self, config_store: ConfigStore, config: AppConfig) -> None:
        super().__init__()
        self._config_store = config_store
        self._config = config
        self._results_dialog: MatchResultsDialog | None = None
        self._last_report_records: list[MatchRecord] = []
        self._scan_started_at: float = 0.0
        self._scan_progress_row: int = -1
        self._live_matches_count: int = 0

        self.setWindowTitle("TJR - Telegram Job Radar")
        self.resize(980, 620)

        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)

        layout = QVBoxLayout(central_widget)

        self.summary_label = QLabel()
        layout.addWidget(self.summary_label)

        top_buttons = QHBoxLayout()
        self.settings_button = QPushButton("Настройки")
        self.settings_button.clicked.connect(self._open_settings)
        top_buttons.addWidget(self.settings_button)

        self.run_button = QPushButton("Проверить чаты")
        self.run_button.clicked.connect(self._run_chat_scan)
        top_buttons.addWidget(self.run_button)

        self.open_last_report_button = QPushButton("Открыть последний отчет")
        self.open_last_report_button.setEnabled(False)
        self.open_last_report_button.clicked.connect(self._open_last_report)
        top_buttons.addWidget(self.open_last_report_button)

        top_buttons.addStretch(1)
        layout.addLayout(top_buttons)

        self.live_matches_value_label = QLabel("0")
        self.live_matches_value_label.setAlignment(Qt.AlignCenter)
        counter_font = self.live_matches_value_label.font()
        counter_font.setPointSize(48)
        counter_font.setBold(True)
        self.live_matches_value_label.setFont(counter_font)
        self.live_matches_value_label.setStyleSheet("color: #e8f4ff;")
        layout.addWidget(self.live_matches_value_label)

        self.live_matches_hint_label = QLabel("Найдено вакансий")
        self.live_matches_hint_label.setAlignment(Qt.AlignCenter)
        self.live_matches_hint_label.setStyleSheet("color: #b0beca;")
        layout.addWidget(self.live_matches_hint_label)

        self.results_list = QListWidget()
        self.results_list.addItem("Нажмите 'Проверить чаты', чтобы начать анализ.")
        self.results_list.addItem(f"Лог-файл: {get_log_path()}")
        enable_smooth_wheel_scroll(self.results_list, speed_factor=0.73, duration_ms=110)
        layout.addWidget(self.results_list)

        self.statusBar().showMessage("Готово")
        self._refresh_summary()

    def _open_settings(self) -> None:
        dialog = SettingsDialog(config=self._config, parent=self)
        if dialog.exec():
            self._config = dialog.config
            self._config_store.save(self._config)
            self._refresh_summary()
            self.statusBar().showMessage("Настройки сохранены", 3000)

    def _refresh_summary(self) -> None:
        tg_configured = bool(self._config.telegram.api_id and self._config.telegram.api_hash)
        active_criteria = sum(
            [
                bool(self._config.job_profile.title_keywords),
                bool(self._config.job_profile.profile_keywords),
                bool(self._config.job_profile.industry_keywords),
            ]
        )
        effective_threshold = max(1, min(self._config.job_profile.min_match_score, max(1, active_criteria)))
        self.summary_label.setText(
            (
                f"Telegram настроен: {'да' if tg_configured else 'нет'} | "
                f"Источников: {len(self._config.selected_chats)} | "
                f"Title/Profile/Industry: "
                f"{len(self._config.job_profile.title_keywords)}/"
                f"{len(self._config.job_profile.profile_keywords)}/"
                f"{len(self._config.job_profile.industry_keywords)} | "
                f"Исключения: {len(self._config.job_profile.exclusion_phrases)} | "
                f"Бан-ссылки: {len(self._config.banned_message_links)} | "
                f"Глубина: {self._config.scan_depth_days} дн | "
                f"Порог: {effective_threshold}/{max(1, active_criteria)} (активные блоки)"
            )
        )

    def _run_chat_scan(self) -> None:
        if not self._config.selected_chats:
            QMessageBox.information(self, "Нет источников", "Добавьте чаты или ссылки в настройках.")
            return

        if not any(
            [
                self._config.job_profile.title_keywords,
                self._config.job_profile.profile_keywords,
                self._config.job_profile.industry_keywords,
            ]
        ):
            QMessageBox.information(self, "Нет критериев", "Добавьте слова поиска в настройках.")
            return

        log_path = reset_log_file()
        logger.info("Chat scan started")
        self.run_button.setEnabled(False)
        self.settings_button.setEnabled(False)
        self.results_list.clear()
        self.results_list.addItem("Старт проверки чатов...")
        self.results_list.addItem(f"Лог-файл: {log_path}")
        self.results_list.addItem("Прогресс: инициализация...")
        self._set_live_matches_count(0)
        self._scan_progress_row = 2
        self._scan_started_at = time.monotonic()

        try:
            report = run_scan(
                self._config,
                request_code=self._request_telegram_code,
                request_password=self._request_telegram_password,
                progress_callback=self._on_scan_progress,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Chat scan failed")
            self.results_list.addItem(f"Ошибка сканирования: {exc}")
            self.statusBar().showMessage("Проверка прервана", 4000)
            QMessageBox.warning(self, "Ошибка сканирования", str(exc))
            return
        finally:
            self.run_button.setEnabled(True)
            self.settings_button.setEnabled(True)

        logger.info(
            "Chat scan completed | chats=%s | messages=%s | matches=%s",
            report.scanned_chats,
            report.scanned_messages,
            len(report.matched_records),
        )

        self.results_list.addItem(
            f"Проверено чатов: {report.scanned_chats}. Проверено сообщений: {report.scanned_messages}."
        )
        self.results_list.addItem(f"Совпадений: {len(report.matched_records)}")
        self._set_live_matches_count(len(report.matched_records))

        if report.matched_records:
            self._last_report_records = list(report.matched_records)
            self.open_last_report_button.setEnabled(True)

        if report.matched_records:
            self._results_dialog = MatchResultsDialog(
                report.matched_records,
                on_ban_message=self._ban_message_link,
                parent=self,
            )
            self._results_dialog.show()
            self.statusBar().showMessage("Проверка завершена: есть совпадения", 3000)
        else:
            self.results_list.addItem("Совпадения не найдены по текущему порогу.")
            self.statusBar().showMessage("Проверка завершена: совпадений нет", 3000)

    def _on_scan_progress(self, progress: ScanProgress) -> None:
        if self._scan_progress_row < 0:
            return
        item = self.results_list.item(self._scan_progress_row)
        if item is None:
            return

        elapsed = max(0.0, time.monotonic() - self._scan_started_at)
        eta_text = "оценка после 1-го чата"
        if progress.completed_chats > 0 and progress.total_chats > progress.completed_chats:
            avg_per_chat = elapsed / progress.completed_chats
            eta_seconds = max(0.0, avg_per_chat * (progress.total_chats - progress.completed_chats))
            eta_text = self._format_eta(eta_seconds)
        elif progress.total_chats > 0 and progress.completed_chats >= progress.total_chats:
            eta_text = "00:00"

        current_step = min(progress.total_chats, max(1, progress.current_chat_index))
        self._set_live_matches_count(progress.matched_count)
        text = (
            f"Прогресс: чат {current_step}/{max(1, progress.total_chats)} | "
            f"обработано сообщений: {progress.scanned_messages} | "
            f"найдено: {progress.matched_count} | "
            f"осталось: ~{eta_text} | "
            f"сейчас: {progress.current_chat}"
        )
        item.setText(text)
        self.statusBar().showMessage(text)
        QApplication.processEvents()

    def _request_telegram_code(self) -> str | None:
        code, ok = QInputDialog.getText(
            self,
            "Код Telegram",
            "Введите код из Telegram:",
            QLineEdit.Normal,
        )
        if not ok:
            return None
        value = code.strip()
        return value or None

    def _request_telegram_password(self) -> str | None:
        password, ok = QInputDialog.getText(
            self,
            "Пароль 2FA",
            "Введите пароль двухфакторной аутентификации:",
            QLineEdit.Password,
        )
        if not ok:
            return None
        value = password.strip()
        return value or None

    def _ban_message_link(self, link: str, is_banned: bool) -> None:
        normalized = link.strip()
        if not normalized:
            return
        if is_banned and normalized not in self._config.banned_message_links:
            self._config.banned_message_links.append(normalized)
            self._config_store.save(self._config)
            self._refresh_summary()
            return
        if not is_banned and normalized in self._config.banned_message_links:
            self._config.banned_message_links.remove(normalized)
            self._config_store.save(self._config)
            self._refresh_summary()

    def _open_last_report(self) -> None:
        if not self._last_report_records:
            QMessageBox.information(self, "Нет отчета", "Пока нет сохраненного отчета с совпадениями.")
            return
        self._results_dialog = MatchResultsDialog(
            list(self._last_report_records),
            on_ban_message=self._ban_message_link,
            parent=self,
        )
        self._results_dialog.show()
        self.statusBar().showMessage("Открыт последний отчет", 3000)

    def _set_live_matches_count(self, value: int) -> None:
        self._live_matches_count = max(0, value)
        self.live_matches_value_label.setText(str(self._live_matches_count))

    @staticmethod
    def _format_eta(seconds: float) -> str:
        total = int(max(0, round(seconds)))
        minutes = total // 60
        secs = total % 60
        return f"{minutes:02d}:{secs:02d}"
