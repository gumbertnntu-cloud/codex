import tempfile
import unittest
from pathlib import Path

from tjr.storage.config_store import AppConfig, ConfigStore, JobProfileSettings, TelegramSettings


class ConfigStoreTests(unittest.TestCase):
    def test_config_store_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "config.json"
            store = ConfigStore(config_path=path)
            config = AppConfig(
                telegram=TelegramSettings(api_id="12345", api_hash="hash-value", phone_number="+79990001122"),
                selected_chats=["@Jobs_Python", "https://t.me/SomeChannel/123"],
                job_profile=JobProfileSettings(
                    title_keywords=["python developer"],
                    profile_keywords=["senior"],
                    industry_keywords=["fintech"],
                    exclusion_phrases=["курсы для директора"],
                    min_match_score=2,
                ),
                scan_depth_days=45,
                banned_message_links=["https://t.me/SomeChannel/123"],
            )

            store.save(config)
            loaded = store.load()

            self.assertEqual(loaded.telegram.api_id, "12345")
            self.assertEqual(loaded.telegram.api_hash, "hash-value")
            self.assertEqual(loaded.telegram.phone_number, "+79990001122")
            self.assertEqual(loaded.selected_chats, ["@Jobs_Python", "https://t.me/SomeChannel/123"])
            self.assertEqual(loaded.job_profile.exclusion_phrases, ["курсы для директора"])
            self.assertEqual(loaded.job_profile.min_match_score, 2)
            self.assertEqual(loaded.scan_depth_days, 45)
            self.assertEqual(loaded.banned_message_links, ["https://t.me/SomeChannel/123"])


if __name__ == "__main__":
    unittest.main()
