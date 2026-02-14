import unittest
from datetime import datetime

from PySide6.QtWidgets import QApplication, QCheckBox

from tjr.core.matching import MatchResult
from tjr.core.scanner import MatchRecord, ScanProgress
from tjr.storage.config_store import AppConfig, JobProfileSettings, TelegramSettings
from tjr.ui.main_window import MainWindow
from tjr.ui.results_window import MatchResultsDialog
from tjr.ui.settings_dialog import SettingsDialog


def _ensure_app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


class SettingsDialogSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = _ensure_app()

    def test_settings_dialog_prefills_fields(self) -> None:
        config = AppConfig(
            telegram=TelegramSettings(api_id="12345", api_hash="secret_hash", phone_number="+79990000000"),
            selected_chats=["@chat_one", "@chat_two"],
            job_profile=JobProfileSettings(
                title_keywords=["python developer", "backend"],
                profile_keywords=["fastapi"],
                industry_keywords=["fintech"],
                exclusion_phrases=["курсы для директора"],
                min_match_score=2,
            ),
        )
        dialog = SettingsDialog(config=config)

        self.assertEqual(dialog.api_id_input.text(), "12345")
        self.assertEqual(dialog.api_hash_input.text(), "secret_hash")
        self.assertEqual(dialog.phone_input.text(), "+79990000000")
        self.assertIn("fastapi", dialog.profile_input.toPlainText())
        self.assertIn("fintech", dialog.industry_input.toPlainText())
        self.assertTrue(hasattr(dialog.profile_input, "_smooth_wheel_scroller"))
        self.assertTrue(hasattr(dialog.industry_input, "_smooth_wheel_scroller"))

        dialog.close()

    def test_settings_dialog_save_updates_config(self) -> None:
        dialog = SettingsDialog(
            config=AppConfig(
                selected_chats=["@new_chat", "https://t.me/chat/1"],
                job_profile=JobProfileSettings(
                    title_keywords=["backend", "director"],
                    exclusion_phrases=["курсы для директора", "рекомендую кандидата"],
                    min_match_score=1,
                ),
                scan_depth_days=45,
            )
        )
        dialog.api_id_input.setText("54321")
        dialog.api_hash_input.setText("myhash123")
        dialog.phone_input.setText("+79991112233")
        dialog.profile_input.setPlainText("senior")
        dialog.industry_input.setPlainText("fintech")

        dialog._handle_save()

        self.assertEqual(dialog.result(), SettingsDialog.DialogCode.Accepted)
        self.assertEqual(dialog.config.telegram.api_id, "54321")
        self.assertEqual(dialog.config.telegram.phone_number, "+79991112233")
        self.assertEqual(dialog.config.selected_chats, ["@new_chat", "https://t.me/chat/1"])
        self.assertEqual(dialog.config.job_profile.title_keywords, ["backend", "director"])
        self.assertEqual(
            dialog.config.job_profile.exclusion_phrases,
            ["курсы для директора", "рекомендую кандидата"],
        )
        self.assertEqual(dialog.config.job_profile.profile_keywords, ["senior"])
        self.assertEqual(dialog.config.job_profile.industry_keywords, ["fintech"])
        self.assertEqual(dialog.config.job_profile.min_match_score, 1)
        self.assertEqual(dialog.config.scan_depth_days, 45)

        dialog.close()

    def test_settings_dialog_keeps_slash_style_on_reopen(self) -> None:
        first_dialog = SettingsDialog(config=AppConfig())
        first_dialog.profile_input.setPlainText("go/системный анализ/product")
        first_dialog._handle_save()
        self.assertEqual(first_dialog.result(), SettingsDialog.DialogCode.Accepted)

        second_dialog = SettingsDialog(config=first_dialog.config)
        self.assertEqual(
            second_dialog.profile_input.toPlainText(),
            "go / системный анализ / product",
        )

        first_dialog.close()
        second_dialog.close()


class MainWindowSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = _ensure_app()

    def test_main_window_defaults_match_current_layout(self) -> None:
        class _DummyConfigStore:
            def save(self, _config: AppConfig) -> None:
                return

        window = MainWindow(
            config_store=_DummyConfigStore(),
            config=AppConfig(telegram=TelegramSettings(api_id="1", api_hash="abcdefgh")),
        )
        self.assertFalse(window.open_last_report_button.isEnabled())
        self.assertEqual(window.live_matches_value_label.text(), "0")
        self.assertEqual(window.settings_button.text(), "Настройки")
        self.assertEqual(window.open_last_report_button.text(), "Отчет")
        self.assertEqual(window.depth_days_value_label.text(), "14")
        self.assertEqual(window.scan_status_value_label.text(), "Chat - / -")
        self.assertEqual(window.scan_status_detail_label.text(), "Готово к запуску")
        self.assertEqual(window.sort_toggle_button.text(), "Сортировка: Дата ↓")
        window.close()

    def test_main_window_updates_live_match_counter_on_progress(self) -> None:
        class _DummyConfigStore:
            def save(self, _config: AppConfig) -> None:
                return

        window = MainWindow(config_store=_DummyConfigStore(), config=AppConfig())
        window._on_scan_progress(
            ScanProgress(
                phase="message_progress",
                current_chat="@jobs",
                current_chat_index=1,
                completed_chats=0,
                total_chats=1,
                scanned_messages=10,
                matched_count=3,
            )
        )
        self.assertEqual(window.live_matches_value_label.text(), "3")
        window.close()

    def test_main_window_applies_quick_settings(self) -> None:
        class _DummyConfigStore:
            def save(self, _config: AppConfig) -> None:
                return

        window = MainWindow(config_store=_DummyConfigStore(), config=AppConfig())
        window.quick_chats_input.setPlainText("@a\n@b")
        window.quick_title_input.setPlainText("ceo/директор")
        window.quick_depth_input.setValue(21)
        window.quick_exclusion_input.setPlainText("курс для директора/рекомендую кандидата")

        window._apply_quick_settings_inputs(show_feedback=False)

        self.assertEqual(window._config.selected_chats, ["@a", "@b"])
        self.assertEqual(window._config.job_profile.title_keywords, ["ceo", "директор"])
        self.assertEqual(
            window._config.job_profile.exclusion_phrases,
            ["курс для директора", "рекомендую кандидата"],
        )
        self.assertEqual(window._config.scan_depth_days, 21)
        self.assertEqual(window.depth_days_value_label.text(), "21")
        window.close()

    def test_main_window_appends_match_to_live_feed(self) -> None:
        class _DummyConfigStore:
            def save(self, _config: AppConfig) -> None:
                return

        match_result = MatchResult(
            score=1,
            active_criteria_count=1,
            excluded=False,
            matched_title=True,
            matched_profile=False,
            matched_industry=False,
            matched_title_terms=["директор"],
            matched_profile_terms=[],
            matched_industry_terms=[],
            matched_exclusion_terms=[],
        )
        record = MatchRecord(
            channel="@jobs",
            published_at=datetime(2026, 1, 3, 12, 0, 0),
            text="message text",
            link="https://t.me/jobs/1",
            match_result=match_result,
        )

        window = MainWindow(config_store=_DummyConfigStore(), config=AppConfig())
        window._on_scan_progress(
            ScanProgress(
                phase="match_found",
                current_chat="@jobs",
                current_chat_index=1,
                completed_chats=0,
                total_chats=1,
                scanned_messages=1,
                matched_count=1,
                latest_match=record,
            )
        )
        self.assertEqual(window.preview_table.rowCount(), 1)
        self.assertEqual(window.preview_table.item(0, 3).text(), "Open")
        window.close()

    def test_main_window_feed_ban_button_toggles_ban_list(self) -> None:
        class _DummyConfigStore:
            def save(self, _config: AppConfig) -> None:
                return

        match_result = MatchResult(
            score=1,
            active_criteria_count=1,
            excluded=False,
            matched_title=True,
            matched_profile=False,
            matched_industry=False,
            matched_title_terms=["директор"],
            matched_profile_terms=[],
            matched_industry_terms=[],
            matched_exclusion_terms=[],
        )
        record = MatchRecord(
            channel="@jobs",
            published_at=datetime(2026, 1, 3, 12, 0, 0),
            text="message text",
            link="https://t.me/jobs/1",
            match_result=match_result,
        )

        window = MainWindow(config_store=_DummyConfigStore(), config=AppConfig())
        window._refresh_preview_table([record])

        ban_button = window.preview_table.cellWidget(0, 0)
        self.assertIsNotNone(ban_button)
        self.assertNotIn(record.link, window._config.banned_message_links)
        ban_button.click()
        self.assertIn(record.link, window._config.banned_message_links)
        ban_button.click()
        self.assertNotIn(record.link, window._config.banned_message_links)
        window.close()

    def test_main_window_opens_cached_report(self) -> None:
        class _DummyConfigStore:
            def save(self, _config: AppConfig) -> None:
                return

        match_result = MatchResult(
            score=1,
            active_criteria_count=1,
            excluded=False,
            matched_title=True,
            matched_profile=False,
            matched_industry=False,
            matched_title_terms=["директор"],
            matched_profile_terms=[],
            matched_industry_terms=[],
            matched_exclusion_terms=[],
        )
        record = MatchRecord(
            channel="cached",
            published_at=datetime(2026, 1, 3, 12, 0, 0),
            text="cached text",
            link="https://t.me/cached/1",
            match_result=match_result,
        )

        window = MainWindow(config_store=_DummyConfigStore(), config=AppConfig())
        window._last_report_records = [record]
        window.open_last_report_button.setEnabled(True)
        window._open_last_report()

        self.assertIsNotNone(window._results_dialog)
        if window._results_dialog is not None:
            self.assertEqual(window._results_dialog.table.rowCount(), 1)
            window._results_dialog.close()
        window.close()


class ResultsWindowSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = _ensure_app()

    def test_results_window_switches_date_sort_order(self) -> None:
        match_result = MatchResult(
            score=1,
            active_criteria_count=1,
            excluded=False,
            matched_title=True,
            matched_profile=False,
            matched_industry=False,
            matched_title_terms=["директор"],
            matched_profile_terms=[],
            matched_industry_terms=[],
            matched_exclusion_terms=[],
        )
        old_record = MatchRecord(
            channel="old",
            published_at=datetime(2026, 1, 1, 12, 0, 0),
            text="old text",
            link="https://t.me/old/1",
            match_result=match_result,
        )
        new_record = MatchRecord(
            channel="new",
            published_at=datetime(2026, 1, 2, 12, 0, 0),
            text="new text",
            link="https://t.me/new/1",
            match_result=match_result,
        )
        dialog = MatchResultsDialog(records=[old_record, new_record])

        self.assertTrue(hasattr(dialog.table, "_smooth_wheel_scroller"))
        self.assertEqual(dialog.table.item(0, 4).text(), "new")
        dialog.sort_combo.setCurrentIndex(1)
        self.assertEqual(dialog.table.item(0, 4).text(), "old")

        dialog.close()

    def test_results_window_ban_checkbox_is_two_way(self) -> None:
        events: list[tuple[str, bool]] = []
        match_result = MatchResult(
            score=1,
            active_criteria_count=1,
            excluded=False,
            matched_title=True,
            matched_profile=False,
            matched_industry=False,
            matched_title_terms=["директор"],
            matched_profile_terms=[],
            matched_industry_terms=[],
            matched_exclusion_terms=[],
        )
        record = MatchRecord(
            channel="chan",
            published_at=datetime(2026, 1, 2, 12, 0, 0),
            text="text",
            link="https://t.me/chan/1",
            match_result=match_result,
        )
        dialog = MatchResultsDialog(
            records=[record],
            on_ban_message=lambda link, is_banned: events.append((link, is_banned)),
        )
        wrapper = dialog.table.cellWidget(0, 0)
        self.assertIsNotNone(wrapper)
        checkbox = wrapper.findChild(QCheckBox) if wrapper is not None else None
        self.assertIsNotNone(checkbox)

        checkbox.setChecked(True)
        checkbox.setChecked(False)

        self.assertEqual(
            events,
            [
                ("https://t.me/chan/1", True),
                ("https://t.me/chan/1", False),
            ],
        )
        dialog.close()


if __name__ == "__main__":
    unittest.main()
