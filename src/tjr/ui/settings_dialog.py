from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

from tjr.core.input_parser import parse_search_terms_text
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

        info_label = QLabel(
            "Каналы/чаты, совпадение по названию, глубина и исключения теперь редактируются на главном экране."
        )
        info_label.setWordWrap(True)
        form.addRow("Быстрые настройки", info_label)

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
            selected_chats=self._config.selected_chats,
            job_profile=JobProfileSettings(
                title_keywords=self._config.job_profile.title_keywords,
                profile_keywords=parse_search_terms_text(self.profile_input.toPlainText()),
                industry_keywords=parse_search_terms_text(self.industry_input.toPlainText()),
                exclusion_phrases=self._config.job_profile.exclusion_phrases,
                min_match_score=self._config.job_profile.min_match_score,
            ),
            scan_depth_days=self._config.scan_depth_days,
            banned_message_links=self._config.banned_message_links,
        )

        self._config = updated
        self.accept()

    @staticmethod
    def _join_terms_for_display(values: list[str]) -> str:
        return " / ".join(values)
