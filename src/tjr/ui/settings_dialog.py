from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
)

from tjr.core.input_parser import parse_chat_sources_text, parse_search_terms_text
from tjr.storage.config_store import AppConfig, JobProfileSettings, TelegramSettings
from tjr.ui.smooth_scroll import enable_smooth_wheel_scroll


class SettingsDialog(QDialog):
    def __init__(self, config: AppConfig, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Настройки TJR")
        self.setMinimumSize(700, 680)
        self._config = config

        root = QVBoxLayout(self)

        form = QFormLayout()

        self.api_id_input = QLineEdit(config.telegram.api_id)
        self.api_id_input.setPlaceholderText("Telegram API ID")
        form.addRow("Telegram API ID", self.api_id_input)

        self.api_hash_input = QLineEdit(config.telegram.api_hash)
        self.api_hash_input.setEchoMode(QLineEdit.Password)
        self.api_hash_input.setPlaceholderText("Telegram API Hash")
        form.addRow("Telegram API Hash", self.api_hash_input)

        self.phone_input = QLineEdit(config.telegram.phone_number)
        self.phone_input.setPlaceholderText("+79990001122")
        form.addRow("Телефон Telegram", self.phone_input)

        self.chats_input = QTextEdit("\n".join(config.selected_chats))
        self.chats_input.setPlaceholderText(
            "@chat1 @chat2, https://t.me/channel/123 или с новой строки"
        )
        self.chats_input.setMinimumHeight(120)
        enable_smooth_wheel_scroll(self.chats_input, speed_factor=0.68, duration_ms=110)
        form.addRow(QLabel("Чаты/ссылки сообщений"), self.chats_input)

        self.title_input = QTextEdit(self._join_terms_for_display(config.job_profile.title_keywords))
        self.title_input.setPlaceholderText(
            "Позиции через /, запятую или новую строку: ceo/директор/операционный директор"
        )
        self.title_input.setMinimumHeight(90)
        enable_smooth_wheel_scroll(self.title_input, speed_factor=0.68, duration_ms=110)
        form.addRow(QLabel("Совпадение по названию"), self.title_input)

        self.profile_input = QTextEdit(self._join_terms_for_display(config.job_profile.profile_keywords))
        self.profile_input.setPlaceholderText(
            "Ключевые слова профиля через /, запятую или новую строку"
        )
        self.profile_input.setMinimumHeight(90)
        enable_smooth_wheel_scroll(self.profile_input, speed_factor=0.68, duration_ms=110)
        form.addRow(QLabel("Совпадение по профилю"), self.profile_input)

        self.industry_input = QTextEdit(self._join_terms_for_display(config.job_profile.industry_keywords))
        self.industry_input.setPlaceholderText(
            "Ключевые слова отрасли через /, запятую или новую строку"
        )
        self.industry_input.setMinimumHeight(90)
        enable_smooth_wheel_scroll(self.industry_input, speed_factor=0.68, duration_ms=110)
        form.addRow(QLabel("Совпадение по отрасли"), self.industry_input)

        self.exclusion_input = QTextEdit(self._join_terms_for_display(config.job_profile.exclusion_phrases))
        self.exclusion_input.setPlaceholderText(
            "Исключающие фразы через /, запятую или новую строку: курсы для директора/рекомендую кандидата"
        )
        self.exclusion_input.setMinimumHeight(90)
        enable_smooth_wheel_scroll(self.exclusion_input, speed_factor=0.68, duration_ms=110)
        form.addRow(QLabel("Исключить, если есть фраза"), self.exclusion_input)

        self.min_score_input = QSpinBox()
        self.min_score_input.setRange(1, 3)
        self.min_score_input.setValue(config.job_profile.min_match_score)
        self.min_score_input.setToolTip(
            "1 = достаточно совпадения по одному активному блоку, 3 = совпасть должны все три блока"
        )
        form.addRow("Минимальный порог совпадения", self.min_score_input)

        self.scan_depth_days_input = QSpinBox()
        self.scan_depth_days_input.setRange(1, 365)
        self.scan_depth_days_input.setValue(config.scan_depth_days)
        self.scan_depth_days_input.setToolTip("За сколько последних дней искать сообщения")
        form.addRow("Глубина поиска (дней назад)", self.scan_depth_days_input)

        root.addLayout(form)

        buttons = QHBoxLayout()
        buttons.addStretch(1)

        cancel_button = QPushButton("Отмена")
        cancel_button.clicked.connect(self.reject)
        buttons.addWidget(cancel_button)

        save_button = QPushButton("Сохранить")
        save_button.clicked.connect(self._handle_save)
        buttons.addWidget(save_button)

        root.addLayout(buttons)

    @property
    def config(self) -> AppConfig:
        return self._config

    def _handle_save(self) -> None:
        api_id = self.api_id_input.text().strip()
        api_hash = self.api_hash_input.text().strip()
        phone_number = self.phone_input.text().strip()

        if (api_id and not api_id.isdigit()) or (api_hash and len(api_hash) < 8):
            QMessageBox.warning(self, "Ошибка валидации", "Проверьте Telegram API ID/API Hash.")
            return

        if phone_number and not phone_number.startswith("+"):
            QMessageBox.warning(self, "Ошибка валидации", "Номер Telegram укажите в формате +79990001122.")
            return

        updated = AppConfig(
            telegram=TelegramSettings(api_id=api_id, api_hash=api_hash, phone_number=phone_number),
            selected_chats=parse_chat_sources_text(self.chats_input.toPlainText()),
            job_profile=JobProfileSettings(
                title_keywords=parse_search_terms_text(self.title_input.toPlainText()),
                profile_keywords=parse_search_terms_text(self.profile_input.toPlainText()),
                industry_keywords=parse_search_terms_text(self.industry_input.toPlainText()),
                exclusion_phrases=parse_search_terms_text(self.exclusion_input.toPlainText()),
                min_match_score=self.min_score_input.value(),
            ),
            scan_depth_days=self.scan_depth_days_input.value(),
            banned_message_links=self._config.banned_message_links,
        )

        self._config = updated
        self.accept()

    @staticmethod
    def _join_terms_for_display(values: list[str]) -> str:
        return " / ".join(values)
