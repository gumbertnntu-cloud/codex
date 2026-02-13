import unittest
from datetime import datetime

from tjr.core.matching import MatchResult
from tjr.core.scanner import MatchRecord, ScanProgress, _dedupe_match_records, run_scan
from tjr.storage.config_store import AppConfig, JobProfileSettings


class ScannerTests(unittest.TestCase):
    def test_run_scan_returns_matches_for_demo_data(self) -> None:
        config = AppConfig(
            selected_chats=["@jobs"],
            job_profile=JobProfileSettings(
                title_keywords=["директор"],
                profile_keywords=["развитие"],
                industry_keywords=["финтех"],
                min_match_score=3,
            ),
        )

        report = run_scan(config)

        self.assertEqual(report.scanned_chats, 1)
        self.assertEqual(report.scanned_messages, 3)
        self.assertEqual(len(report.matched_records), 1)
        self.assertEqual(report.matched_records[0].channel, "@jobs")
        self.assertIn("https://t.me/jobs/", report.matched_records[0].link)

    def test_run_scan_excludes_messages_by_exclusion_phrase(self) -> None:
        config = AppConfig(
            selected_chats=["@jobs"],
            job_profile=JobProfileSettings(
                title_keywords=["директор"],
                profile_keywords=["развитие"],
                industry_keywords=["финтех"],
                exclusion_phrases=["директора по развитию"],
                min_match_score=3,
            ),
        )

        report = run_scan(config)

        self.assertEqual(report.scanned_chats, 1)
        self.assertEqual(report.scanned_messages, 3)
        self.assertEqual(len(report.matched_records), 0)

    def test_dedupe_match_records_by_link(self) -> None:
        result = MatchResult(
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
        first = MatchRecord(
            channel="@rudakovahr",
            published_at=datetime(2026, 2, 13, 10, 0, 0),
            text="Директор по продукту",
            link="https://t.me/rudakovahr/7378",
            match_result=result,
        )
        second = MatchRecord(
            channel="@rudakovahr",
            published_at=datetime(2026, 2, 13, 10, 0, 1),
            text="Директор по продукту (дубль)",
            link="https://t.me/rudakovahr/7378",
            match_result=result,
        )

        deduped = _dedupe_match_records([first, second])
        self.assertEqual(len(deduped), 1)
        self.assertEqual(deduped[0].link, "https://t.me/rudakovahr/7378")

    def test_run_scan_emits_progress_callback(self) -> None:
        events: list[ScanProgress] = []
        config = AppConfig(
            selected_chats=["@jobs"],
            job_profile=JobProfileSettings(
                title_keywords=["директор"],
                profile_keywords=["развитие"],
                industry_keywords=["финтех"],
                min_match_score=3,
            ),
        )

        report = run_scan(config, progress_callback=lambda progress: events.append(progress))

        self.assertEqual(report.scanned_chats, 1)
        self.assertGreaterEqual(len(events), 1)
        self.assertEqual(events[-1].total_chats, 1)
        self.assertGreaterEqual(events[-1].scanned_messages, 1)
        self.assertGreaterEqual(events[-1].matched_count, 1)

if __name__ == "__main__":
    unittest.main()
