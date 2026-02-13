import unittest

from tjr.core.matching import evaluate_message
from tjr.storage.config_store import JobProfileSettings


class MatchingTests(unittest.TestCase):
    def test_evaluate_message_returns_expected_score(self) -> None:
        profile = JobProfileSettings(
            title_keywords=["developer"],
            profile_keywords=["fastapi"],
            industry_keywords=["fintech"],
            min_match_score=2,
        )

        result = evaluate_message("Senior Python developer for fintech. FastAPI stack.", profile)

        self.assertEqual(result.score, 3)
        self.assertFalse(result.excluded)
        self.assertTrue(result.matched_title)
        self.assertTrue(result.matched_profile)
        self.assertTrue(result.matched_industry)
        self.assertEqual(result.matched_title_terms, ["developer"])
        self.assertEqual(result.matched_profile_terms, ["fastapi"])
        self.assertEqual(result.matched_industry_terms, ["fintech"])
        self.assertEqual(result.matched_exclusion_terms, [])

    def test_evaluate_message_matches_russian_inflections(self) -> None:
        profile = JobProfileSettings(
            title_keywords=["директор"],
            profile_keywords=["развитие"],
            industry_keywords=["финтех"],
            min_match_score=2,
        )

        result = evaluate_message(
            "В продуктовую команду ищем директора по развитию в сфере финтеха.",
            profile,
        )

        self.assertEqual(result.score, 3)
        self.assertFalse(result.excluded)
        self.assertIn("директор", result.matched_title_terms)
        self.assertIn("развитие", result.matched_profile_terms)
        self.assertIn("финтех", result.matched_industry_terms)

    def test_evaluate_message_excludes_by_phrase(self) -> None:
        profile = JobProfileSettings(
            title_keywords=["директор"],
            profile_keywords=[],
            industry_keywords=[],
            exclusion_phrases=["рекомендую кандидата", "курсы для директора"],
            min_match_score=1,
        )

        result = evaluate_message(
            "Рекомендую кандидата на роль директора, отличный опыт в продажах.",
            profile,
        )

        self.assertTrue(result.excluded)
        self.assertIn("рекомендую кандидата", result.matched_exclusion_terms)

    def test_evaluate_message_excludes_by_system_noise_phrase(self) -> None:
        profile = JobProfileSettings(
            title_keywords=["директор"],
            profile_keywords=[],
            industry_keywords=[],
            exclusion_phrases=[],
            min_match_score=1,
        )

        result = evaluate_message(
            "Рекомендую кандидата на позицию коммерческого директора, опыт 12 лет.",
            profile,
        )

        self.assertTrue(result.excluded)
        self.assertIn("рекомендую кандидата", result.matched_exclusion_terms)

    def test_evaluate_message_excludes_course_messages(self) -> None:
        profile = JobProfileSettings(
            title_keywords=["директор"],
            profile_keywords=[],
            industry_keywords=[],
            exclusion_phrases=[],
            min_match_score=1,
        )

        result = evaluate_message(
            "Курсы для директоров продаж. Старт потока в марте.",
            profile,
        )

        self.assertTrue(result.excluded)
        self.assertIn("курсы для", result.matched_exclusion_terms)

    def test_evaluate_message_does_not_exclude_regular_vacancy(self) -> None:
        profile = JobProfileSettings(
            title_keywords=["директор"],
            profile_keywords=["продажи"],
            industry_keywords=[],
            exclusion_phrases=[],
            min_match_score=1,
        )

        result = evaluate_message(
            "Ищем коммерческого директора. Обучение и доступ к корпоративной библиотеке.",
            profile,
        )

        self.assertFalse(result.excluded)
        self.assertGreaterEqual(result.score, 1)


if __name__ == "__main__":
    unittest.main()
