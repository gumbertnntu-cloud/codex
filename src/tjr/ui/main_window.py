from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

from PySide6.QtCore import QRectF, Qt, QUrl
from PySide6.QtGui import QBrush, QColor, QDesktopServices, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QApplication
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QGridLayout,
    QHeaderView,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from tjr.core.input_parser import parse_chat_sources_text, parse_search_terms_text
from tjr.core.logging_setup import reset_log_file
from tjr.core.scanner import MatchRecord, ScanProgress, run_scan
from tjr.storage.config_store import AppConfig, ConfigStore
from tjr.ui.results_window import MatchResultsDialog
from tjr.ui.settings_dialog import SettingsDialog
from tjr.ui.smooth_scroll import enable_smooth_wheel_scroll

logger = logging.getLogger(__name__)


class RoundedImageLabel(QLabel):
    def __init__(self, radius: int = 14, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._radius = radius
        self._source_pixmap = QPixmap()
        self._fallback_text = "TJR"
        self.setAlignment(Qt.AlignCenter)

    def set_source_pixmap(self, pixmap: QPixmap) -> None:
        self._source_pixmap = pixmap
        self.update()

    def set_fallback_text(self, text: str) -> None:
        self._fallback_text = text
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)

        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        path = QPainterPath()
        path.addRoundedRect(rect, self._radius, self._radius)
        painter.setClipPath(path)

        if not self._source_pixmap.isNull():
            src = self._source_pixmap
            dst_ratio = rect.width() / max(1.0, rect.height())
            src_ratio = src.width() / max(1, src.height())
            if src_ratio > dst_ratio:
                target_h = rect.height()
                target_w = target_h * src_ratio
            else:
                target_w = rect.width()
                target_h = target_w / src_ratio
            x = rect.x() + (rect.width() - target_w) / 2.0
            y = rect.y() + (rect.height() - target_h) / 2.0
            target = QRectF(x, y, target_w, target_h)
            painter.drawPixmap(target, src, QRectF(src.rect()))
            painter.fillRect(rect, QColor(8, 18, 33, 35))
        else:
            painter.fillRect(rect, QColor("#0d1826"))
            painter.setPen(QColor("#7f9dbf"))
            painter.drawText(rect, Qt.AlignCenter, self._fallback_text)

        painter.setClipping(False)
        painter.setPen(QPen(QColor("#1a2b3e"), 1))
        painter.drawRoundedRect(rect, self._radius, self._radius)


class MainWindow(QMainWindow):
    def __init__(self, config_store: ConfigStore, config: AppConfig) -> None:
        super().__init__()
        self._config_store = config_store
        self._config = config
        self._results_dialog: MatchResultsDialog | None = None
        self._last_report_records: list[MatchRecord] = []
        self._live_feed_records: list[MatchRecord] = []
        self._scan_started_at: float = 0.0
        self._live_matches_count: int = 0
        self._cancel_scan_requested = False
        self._is_scanning = False

        self.setWindowTitle("TJR - Telegram Job Radar")
        self.resize(1440, 900)
        self._apply_theme()

        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        root = QHBoxLayout(central_widget)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(18)

        left_panel = QFrame()
        left_panel.setObjectName("LeftPanel")
        left_panel.setFixedWidth(360)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(18, 18, 18, 18)
        left_layout.setSpacing(12)

        self.left_hero_art_label = RoundedImageLabel(radius=14)
        self.left_hero_art_label.setObjectName("LeftHeroArt")
        self.left_hero_art_label.setMinimumHeight(204)
        self.left_hero_art_label.setMaximumHeight(204)
        left_layout.addWidget(self.left_hero_art_label)

        quick_settings_card = QFrame()
        quick_settings_card.setObjectName("QuickSettingsCard")
        quick_settings_layout = QVBoxLayout(quick_settings_card)
        quick_settings_layout.setContentsMargins(14, 12, 14, 12)
        quick_settings_layout.setSpacing(10)

        quick_title = QLabel("БЫСТРЫЕ НАСТРОЙКИ СКАНА")
        quick_title.setObjectName("HeroTitle")
        quick_settings_layout.addWidget(quick_title)

        quick_chats_label = QLabel("Каналы/чаты")
        quick_chats_label.setObjectName("QuickLabel")
        quick_settings_layout.addWidget(quick_chats_label)

        self.quick_chats_input = QTextEdit()
        self.quick_chats_input.setPlaceholderText("@chat_one @chat_two или https://t.me/channel/123")
        self.quick_chats_input.setMinimumHeight(84)
        enable_smooth_wheel_scroll(self.quick_chats_input, speed_factor=0.68, duration_ms=110)
        quick_settings_layout.addWidget(self.quick_chats_input)

        quick_title_label = QLabel("Совпадение по названию")
        quick_title_label.setObjectName("QuickLabel")
        quick_settings_layout.addWidget(quick_title_label)

        self.quick_title_input = QTextEdit()
        self.quick_title_input.setPlaceholderText("ceo / исполнительный директор / операционный директор")
        self.quick_title_input.setMinimumHeight(72)
        enable_smooth_wheel_scroll(self.quick_title_input, speed_factor=0.68, duration_ms=110)
        quick_settings_layout.addWidget(self.quick_title_input)

        quick_depth_label = QLabel("Глубина поиска (дней)")
        quick_depth_label.setObjectName("QuickLabel")
        quick_settings_layout.addWidget(quick_depth_label)

        self.quick_depth_input = QSpinBox()
        self.quick_depth_input.setRange(1, 365)
        self.quick_depth_input.setToolTip("За сколько последних дней смотреть сообщения")
        self.quick_depth_input.setFixedWidth(132)
        depth_row = QHBoxLayout()
        depth_row.setContentsMargins(0, 0, 0, 0)
        depth_row.addWidget(self.quick_depth_input)
        depth_row.addStretch(1)
        quick_settings_layout.addLayout(depth_row)

        quick_exclusion_label = QLabel("Исключения")
        quick_exclusion_label.setObjectName("QuickLabel")
        quick_settings_layout.addWidget(quick_exclusion_label)

        self.quick_exclusion_input = QTextEdit()
        self.quick_exclusion_input.setPlaceholderText("курсы для директора / рекомендую кандидата")
        self.quick_exclusion_input.setMinimumHeight(72)
        enable_smooth_wheel_scroll(self.quick_exclusion_input, speed_factor=0.68, duration_ms=110)
        quick_settings_layout.addWidget(self.quick_exclusion_input)

        apply_quick_settings_button = QPushButton("Применить")
        apply_quick_settings_button.setObjectName("GhostButton")
        apply_quick_settings_button.clicked.connect(self._apply_quick_settings_inputs)
        quick_settings_layout.addWidget(apply_quick_settings_button, alignment=Qt.AlignLeft)
        left_layout.addWidget(quick_settings_card)

        left_layout.addStretch(1)

        self.run_button = QPushButton("Start Scan")
        self.run_button.setObjectName("StartButton")
        self.run_button.clicked.connect(self._run_chat_scan)
        left_layout.addWidget(self.run_button)

        self.stop_button = QPushButton("Stop Scan")
        self.stop_button.setObjectName("StopButton")
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self._request_stop_scan)
        left_layout.addWidget(self.stop_button)

        right_panel = QFrame()
        right_panel.setObjectName("RightPanel")
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(20, 20, 20, 20)
        right_layout.setSpacing(14)

        header = QFrame()
        header.setObjectName("TopBar")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(14, 8, 14, 8)

        main_title = QLabel("Main Control")
        main_title.setObjectName("MainTitle")
        header_layout.addWidget(main_title)
        header_layout.addStretch(1)

        self.settings_button = QPushButton("Настройки")
        self.settings_button.setObjectName("GhostButton")
        self.settings_button.clicked.connect(self._open_settings)
        header_layout.addWidget(self.settings_button)

        self.open_last_report_button = QPushButton("Отчет")
        self.open_last_report_button.setObjectName("GhostButton")
        self.open_last_report_button.setEnabled(False)
        self.open_last_report_button.clicked.connect(self._open_last_report)
        header_layout.addWidget(self.open_last_report_button)
        right_layout.addWidget(header)

        hero_row = QHBoxLayout()
        hero_row.setSpacing(14)

        hero_counter = QFrame()
        hero_counter.setObjectName("HeroCounter")
        hero_counter_layout = QVBoxLayout(hero_counter)
        hero_counter_layout.setContentsMargins(18, 14, 18, 14)
        hero_counter_layout.setSpacing(4)
        hero_counter_title = QLabel("LIVE MATCH COUNTER")
        hero_counter_title.setObjectName("HeroTitle")
        hero_counter_layout.addWidget(hero_counter_title)

        self.live_matches_value_label = QLabel("0")
        self.live_matches_value_label.setAlignment(Qt.AlignLeft)
        counter_font = self.live_matches_value_label.font()
        counter_font.setPointSize(90)
        counter_font.setBold(True)
        self.live_matches_value_label.setFont(counter_font)
        self.live_matches_value_label.setObjectName("LiveCounter")
        hero_counter_layout.addWidget(self.live_matches_value_label)

        self.live_matches_hint_label = QLabel("Vacancies matched right now")
        self.live_matches_hint_label.setAlignment(Qt.AlignLeft)
        self.live_matches_hint_label.setObjectName("LiveCounterHint")
        hero_counter_layout.addWidget(self.live_matches_hint_label)
        hero_counter_layout.addStretch(1)

        hero_row.addWidget(hero_counter, stretch=2)

        hero_status = QFrame()
        hero_status.setObjectName("HeroStatus")
        hero_status_layout = QVBoxLayout(hero_status)
        hero_status_layout.setContentsMargins(18, 14, 18, 14)
        hero_status_layout.setSpacing(10)
        status_title = QLabel("SCAN STATUS")
        status_title.setObjectName("HeroTitle")
        hero_status_layout.addWidget(status_title)

        self.scan_status_value_label = QLabel("Chat - / -")
        self.scan_status_value_label.setObjectName("StatusPrimary")
        hero_status_layout.addWidget(self.scan_status_value_label)

        self.scan_status_detail_label = QLabel("Готово к запуску")
        self.scan_status_detail_label.setObjectName("StatusSecondary")
        self.scan_status_detail_label.setWordWrap(True)
        hero_status_layout.addWidget(self.scan_status_detail_label)
        hero_status_layout.addStretch(1)

        hero_row.addWidget(hero_status, stretch=1)
        right_layout.addLayout(hero_row)

        metrics_grid = QGridLayout()
        metrics_grid.setHorizontalSpacing(14)
        metrics_grid.setVerticalSpacing(14)

        channels_card, self.channels_value_label = self._build_metric_card("ACTIVE CHANNELS", "0")
        depth_card, self.depth_days_value_label = self._build_metric_card("ГЛУБИНА (ДНИ)", str(self._config.scan_depth_days))
        blocked_card, self.blocked_value_label = self._build_metric_card("NOISE BLOCKED", "0")

        metrics_grid.addWidget(channels_card, 0, 0)
        metrics_grid.addWidget(depth_card, 0, 1)
        metrics_grid.addWidget(blocked_card, 0, 2)
        right_layout.addLayout(metrics_grid)

        feed_card = QFrame()
        feed_card.setObjectName("FeedCard")
        feed_layout = QVBoxLayout(feed_card)
        feed_layout.setContentsMargins(16, 12, 16, 16)
        feed_layout.setSpacing(10)

        feed_title = QLabel("MATCH FEED")
        feed_title.setObjectName("HeroTitle")
        feed_layout.addWidget(feed_title)

        self.preview_table = QTableWidget()
        self.preview_table.setObjectName("FeedTable")
        self.preview_table.setColumnCount(5)
        self.preview_table.setHorizontalHeaderLabels(["DATE", "MESSAGE", "LINK", "CHANNEL", "MATCHES"])
        self.preview_table.verticalHeader().setVisible(False)
        self.preview_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.preview_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.preview_table.setWordWrap(True)
        self.preview_table.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.preview_table.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.preview_table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.preview_table.setColumnWidth(0, 155)
        self.preview_table.setColumnWidth(1, 460)
        self.preview_table.setColumnWidth(2, 140)
        self.preview_table.setColumnWidth(3, 150)
        self.preview_table.setColumnWidth(4, 190)
        self.preview_table.cellClicked.connect(self._on_preview_cell_clicked)
        enable_smooth_wheel_scroll(self.preview_table, speed_factor=0.73, duration_ms=110)

        feed_layout.addWidget(self.preview_table, stretch=1)
        right_layout.addWidget(feed_card, stretch=1)

        root.addWidget(left_panel)
        root.addWidget(right_panel, stretch=1)

        self.statusBar().showMessage("Готово")
        self._populate_quick_settings_inputs()
        self._refresh_left_hero_art()
        self._refresh_preview_table([])

    def _open_settings(self) -> None:
        self._apply_quick_settings_inputs(show_feedback=False)
        dialog = SettingsDialog(config=self._config, parent=self)
        if dialog.exec():
            self._config = dialog.config
            self._config_store.save(self._config)
            self._populate_quick_settings_inputs()
            self.blocked_value_label.setText(str(len(self._config.banned_message_links)))
            self.channels_value_label.setText(str(len(self._config.selected_chats)))
            self.depth_days_value_label.setText(str(self._config.scan_depth_days))
            self.statusBar().showMessage("Настройки сохранены", 3000)

    @staticmethod
    def _resolve_asset_path(relative_path: str) -> Path | None:
        relative = Path(relative_path)
        candidates: list[Path] = []
        if getattr(sys, "frozen", False):
            meipass = getattr(sys, "_MEIPASS", None)
            if meipass:
                candidates.append(Path(meipass) / relative)
        candidates.append(Path(__file__).resolve().parents[3] / relative)
        for candidate in candidates:
            if candidate.exists():
                return candidate
        return None

    def _refresh_left_hero_art(self) -> None:
        asset_path = self._resolve_asset_path("assets/illustrations/left-hero-v1.png")
        if asset_path is None:
            self.left_hero_art_label.set_source_pixmap(QPixmap())
            self.left_hero_art_label.set_fallback_text("TJR")
            return

        pixmap = QPixmap(str(asset_path))
        if pixmap.isNull():
            self.left_hero_art_label.set_source_pixmap(QPixmap())
            self.left_hero_art_label.set_fallback_text("TJR")
            return

        self.left_hero_art_label.set_source_pixmap(pixmap)

    def _populate_quick_settings_inputs(self) -> None:
        self.quick_chats_input.setPlainText("\n".join(self._config.selected_chats))
        self.quick_title_input.setPlainText(self._join_terms_for_display(self._config.job_profile.title_keywords))
        self.quick_depth_input.setValue(self._config.scan_depth_days)
        self.quick_exclusion_input.setPlainText(self._join_terms_for_display(self._config.job_profile.exclusion_phrases))

    def _apply_quick_settings_inputs(self, checked: bool = False, *, show_feedback: bool = True) -> bool:
        del checked
        self._config.selected_chats = parse_chat_sources_text(self.quick_chats_input.toPlainText())
        self._config.job_profile.title_keywords = parse_search_terms_text(self.quick_title_input.toPlainText())
        self._config.job_profile.exclusion_phrases = parse_search_terms_text(self.quick_exclusion_input.toPlainText())
        self._config.scan_depth_days = self.quick_depth_input.value()
        self._config_store.save(self._config)

        self._populate_quick_settings_inputs()
        self.channels_value_label.setText(str(len(self._config.selected_chats)))
        self.blocked_value_label.setText(str(len(self._config.banned_message_links)))
        self.depth_days_value_label.setText(str(self._config.scan_depth_days))
        if show_feedback:
            self.statusBar().showMessage("Быстрые настройки применены", 2500)
        return True

    def _run_chat_scan(self) -> None:
        if self._is_scanning:
            return
        self._apply_quick_settings_inputs(show_feedback=False)

        if not self._config.selected_chats:
            QMessageBox.information(self, "Нет источников", "Добавьте чаты или ссылки в блоке быстрых настроек.")
            return

        if not any(
            [
                self._config.job_profile.title_keywords,
                self._config.job_profile.profile_keywords,
                self._config.job_profile.industry_keywords,
            ]
        ):
            QMessageBox.information(
                self,
                "Нет критериев",
                "Добавьте слова поиска в быстрых настройках или заполните Профиль/Отрасль в окне Настройки.",
            )
            return

        reset_log_file()
        logger.info("Chat scan started")

        self._is_scanning = True
        self._cancel_scan_requested = False
        self._scan_started_at = time.monotonic()

        self.run_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.stop_button.setText("Stop Scan")
        self.settings_button.setEnabled(False)

        self._live_feed_records = []
        self._refresh_preview_table([])
        self._set_live_matches_count(0)

        self.scan_status_value_label.setText(f"Chat 0 / {max(1, len(self._config.selected_chats))}")
        self.scan_status_detail_label.setText("Старт сканирования...")
        self.channels_value_label.setText(str(len(self._config.selected_chats)))
        self.blocked_value_label.setText(str(len(self._config.banned_message_links)))
        self.depth_days_value_label.setText(str(self._config.scan_depth_days))

        try:
            report = run_scan(
                self._config,
                request_code=self._request_telegram_code,
                request_password=self._request_telegram_password,
                progress_callback=self._on_scan_progress,
                should_stop=self._should_stop_scan,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Chat scan failed")
            self.statusBar().showMessage("Проверка прервана", 4000)
            self.scan_status_detail_label.setText(f"Ошибка: {exc}")
            QMessageBox.warning(self, "Ошибка сканирования", str(exc))
            return
        finally:
            self._is_scanning = False
            self.run_button.setEnabled(True)
            self.stop_button.setEnabled(False)
            self.stop_button.setText("Stop Scan")
            self.settings_button.setEnabled(True)

        logger.info(
            "Chat scan completed | chats=%s | messages=%s | matches=%s | canceled=%s",
            report.scanned_chats,
            report.scanned_messages,
            len(report.matched_records),
            report.canceled,
        )

        self._set_live_matches_count(len(report.matched_records))
        self._live_feed_records = list(report.matched_records)
        self._refresh_preview_table(self._live_feed_records)

        self.depth_days_value_label.setText(str(self._config.scan_depth_days))

        self.scan_status_value_label.setText(
            f"Chat {report.scanned_chats} / {max(report.scanned_chats, len(self._config.selected_chats))}"
        )

        if report.canceled:
            self.scan_status_detail_label.setText(
                f"Остановлено пользователем. Проверено сообщений: {report.scanned_messages}"
            )
            self.statusBar().showMessage("Сканирование остановлено", 4000)
        else:
            self.scan_status_detail_label.setText(
                f"Завершено. Чатов: {report.scanned_chats}, сообщений: {report.scanned_messages}"
            )
            self.statusBar().showMessage("Проверка завершена", 3000)

        if report.matched_records:
            self._last_report_records = list(report.matched_records)
            self.open_last_report_button.setEnabled(True)

    def _on_scan_progress(self, progress: ScanProgress) -> None:
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
        self.scan_status_value_label.setText(f"Chat {current_step} / {max(1, progress.total_chats)}")
        self.scan_status_detail_label.setText(
            f"{progress.current_chat} | scanned: {progress.scanned_messages} | ETA: {eta_text}"
        )

        self.channels_value_label.setText(str(max(0, progress.total_chats)))
        self.blocked_value_label.setText(str(len(self._config.banned_message_links)))
        self.depth_days_value_label.setText(str(self._config.scan_depth_days))

        if progress.phase == "match_found" and progress.latest_match is not None:
            self._append_live_match(progress.latest_match)

        self.statusBar().showMessage(
            (
                f"Прогресс: чат {current_step}/{max(1, progress.total_chats)} | "
                f"сообщений: {progress.scanned_messages} | найдено: {progress.matched_count} | ETA: {eta_text}"
            )
        )
        QApplication.processEvents()

    def _append_live_match(self, record: MatchRecord) -> None:
        key = self._record_key(record)
        known_keys = {self._record_key(item) for item in self._live_feed_records}
        if key in known_keys:
            return
        self._live_feed_records.insert(0, record)
        if len(self._live_feed_records) > 120:
            self._live_feed_records = self._live_feed_records[:120]
        self._refresh_preview_table(self._live_feed_records)

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
            self.blocked_value_label.setText(str(len(self._config.banned_message_links)))
            return
        if not is_banned and normalized in self._config.banned_message_links:
            self._config.banned_message_links.remove(normalized)
            self._config_store.save(self._config)
            self.blocked_value_label.setText(str(len(self._config.banned_message_links)))

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

    def _request_stop_scan(self) -> None:
        if not self._is_scanning:
            return
        self._cancel_scan_requested = True
        self.stop_button.setEnabled(False)
        self.stop_button.setText("Stopping...")
        self.scan_status_detail_label.setText("Остановка по запросу пользователя...")
        logger.info("Scan stop requested by user")
        self.statusBar().showMessage("Остановка сканирования...")
        QApplication.processEvents()

    def _should_stop_scan(self) -> bool:
        return self._cancel_scan_requested

    def _on_preview_cell_clicked(self, row: int, column: int) -> None:
        if column != 2:
            return
        item = self.preview_table.item(row, column)
        if item is None:
            return
        link = item.data(Qt.UserRole)
        if isinstance(link, str) and link:
            QDesktopServices.openUrl(QUrl(link))

    def _refresh_preview_table(self, records: list[MatchRecord]) -> None:
        ordered = sorted(records, key=lambda item: item.published_at, reverse=True)
        visible = ordered[:40]
        self.preview_table.clearContents()
        self.preview_table.setRowCount(len(visible))

        for row, record in enumerate(visible):
            dt_item = QTableWidgetItem(record.published_at.strftime("%Y-%m-%d %H:%M"))
            message_item = QTableWidgetItem(self._compact_message(record.text))
            message_item.setToolTip(record.text)

            link_item = QTableWidgetItem("Open")
            link_item.setData(Qt.UserRole, record.link)
            link_item.setToolTip(record.link)
            link_item.setForeground(QBrush(QColor("#7de0bb")))

            channel_item = QTableWidgetItem(record.channel)
            if record.link:
                channel_item.setToolTip(record.link)
            channel_item.setForeground(QBrush(QColor("#7de0bb")))

            matches_item = QTableWidgetItem(self._compact_terms(record))
            matches_item.setForeground(QBrush(QColor("#7de0bb")))

            self.preview_table.setItem(row, 0, dt_item)
            self.preview_table.setItem(row, 1, message_item)
            self.preview_table.setItem(row, 2, link_item)
            self.preview_table.setItem(row, 3, channel_item)
            self.preview_table.setItem(row, 4, matches_item)
            self.preview_table.resizeRowToContents(row)

    def _set_live_matches_count(self, value: int) -> None:
        self._live_matches_count = max(0, value)
        self.live_matches_value_label.setText(str(self._live_matches_count))

    @staticmethod
    def _compact_message(text: str, limit: int = 90) -> str:
        one_line = " ".join((text or "").split())
        if len(one_line) <= limit:
            return one_line
        return one_line[: limit - 3] + "..."

    @staticmethod
    def _compact_terms(record: MatchRecord) -> str:
        terms = (
            record.match_result.matched_title_terms
            + record.match_result.matched_profile_terms
            + record.match_result.matched_industry_terms
        )
        if not terms:
            return "-"
        unique = list(dict.fromkeys(terms))
        return " • ".join(unique[:3])

    @staticmethod
    def _join_terms_for_display(values: list[str]) -> str:
        return " / ".join(values)

    @staticmethod
    def _record_key(record: MatchRecord) -> str:
        link = record.link.strip().lower()
        if link:
            return f"link:{link}"
        return f"fallback:{record.channel.lower()}|{record.published_at.isoformat()}|{record.text.lower()}"

    @staticmethod
    def _build_metric_card(title: str, value: str) -> tuple[QFrame, QLabel]:
        card = QFrame()
        card.setObjectName("MetricCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(6)

        title_label = QLabel(title)
        title_label.setObjectName("MetricTitle")
        value_label = QLabel(value)
        value_label.setObjectName("MetricValue")

        layout.addWidget(title_label)
        layout.addWidget(value_label)
        layout.addStretch(1)
        return card, value_label

    @staticmethod
    def _format_eta(seconds: float) -> str:
        total = int(max(0, round(seconds)))
        minutes = total // 60
        secs = total % 60
        return f"{minutes:02d}:{secs:02d}"

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._refresh_left_hero_art()

    def _apply_theme(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow {
                background: #06090f;
                color: #e8f2ff;
            }
            QStatusBar {
                background: #0b1320;
                color: #9ab5d2;
                border-top: 1px solid #1b2a3b;
            }
            #LeftPanel, #RightPanel {
                background: #0b1420;
                border-radius: 22px;
            }
            #LeftHeroArt {
                color: #7f9dbf;
                font-size: 20px;
                font-weight: 800;
            }
            #TopBar {
                background: #121e2d;
                border-radius: 14px;
            }
            #MainTitle {
                color: #f3f9ff;
                font-size: 28px;
                font-weight: 800;
            }
            #GhostButton {
                background: #16324d;
                color: #d7eafc;
                border: none;
                border-radius: 10px;
                padding: 8px 16px;
                font-size: 13px;
                font-weight: 700;
            }
            #GhostButton:disabled {
                color: #63809b;
                background: #122436;
            }
            #StartButton {
                background: #1cc587;
                color: #042118;
                border: none;
                border-radius: 12px;
                padding: 12px 16px;
                font-size: 17px;
                font-weight: 800;
            }
            #StartButton:disabled {
                background: #25644d;
                color: #9fd0ba;
            }
            #StopButton {
                background: #17314a;
                color: #d4e8fb;
                border: none;
                border-radius: 12px;
                padding: 12px 16px;
                font-size: 16px;
                font-weight: 700;
            }
            #StopButton:disabled {
                background: #112638;
                color: #6f8ea9;
            }
            #HeroCounter, #HeroStatus, #MetricCard, #FeedCard, #QuickSettingsCard {
                background: #0f1b2a;
                border-radius: 18px;
            }
            #HeroCounter {
                background: #122338;
            }
            #HeroTitle {
                color: #86abd0;
                font-size: 12px;
                font-weight: 700;
                letter-spacing: 0.5px;
            }
            #LiveCounter {
                color: #ffffff;
                font-weight: 900;
            }
            #LiveCounterHint {
                color: #b7d6f6;
                font-size: 20px;
                font-weight: 600;
            }
            #StatusPrimary {
                color: #ffffff;
                font-size: 18px;
                font-weight: 800;
            }
            #StatusSecondary {
                color: #a7c2de;
                font-size: 14px;
                font-weight: 600;
            }
            #MetricTitle {
                color: #7f9dbf;
                font-size: 12px;
                font-weight: 700;
                letter-spacing: 0.4px;
            }
            #MetricValue {
                color: #f3f9ff;
                font-size: 44px;
                font-weight: 900;
            }
            #QuickSettingsCard QLabel {
                color: #c9ddf2;
                font-size: 13px;
                font-weight: 600;
            }
            #QuickSettingsCard QTextEdit, #QuickSettingsCard QSpinBox {
                background: #0d1826;
                color: #e6f1ff;
                border: 1px solid #1a2b3e;
                border-radius: 8px;
                padding: 6px 8px;
                font-size: 13px;
            }
            #QuickSettingsCard QSpinBox::up-button, #QuickSettingsCard QSpinBox::down-button {
                width: 20px;
            }
            #FeedTable {
                background: #0d1826;
                border: 1px solid #1a2b3e;
                border-radius: 10px;
                gridline-color: #1c2c3f;
                color: #e6f1ff;
                font-size: 13px;
            }
            #FeedTable QHeaderView::section {
                background: #14273b;
                color: #8fb4d8;
                border: none;
                padding: 10px 8px;
                font-size: 12px;
                font-weight: 700;
            }
            #FeedTable::item {
                padding: 8px;
            }
            QToolTip {
                background: #122338;
                color: #f3f9ff;
                border: 1px solid #2c4866;
                padding: 8px 10px;
                font-size: 16px;
                font-weight: 600;
            }
            """
        )
