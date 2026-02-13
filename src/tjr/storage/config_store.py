from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from tjr.storage.app_paths import config_path as default_config_path


@dataclass(slots=True)
class TelegramSettings:
    api_id: str = ""
    api_hash: str = ""
    phone_number: str = ""


@dataclass(slots=True)
class JobProfileSettings:
    title_keywords: list[str] = field(default_factory=list)
    profile_keywords: list[str] = field(default_factory=list)
    industry_keywords: list[str] = field(default_factory=list)
    exclusion_phrases: list[str] = field(default_factory=list)
    min_match_score: int = 2


@dataclass(slots=True)
class AppConfig:
    telegram: TelegramSettings = field(default_factory=TelegramSettings)
    selected_chats: list[str] = field(default_factory=list)
    job_profile: JobProfileSettings = field(default_factory=JobProfileSettings)
    scan_depth_days: int = 14
    banned_message_links: list[str] = field(default_factory=list)


class ConfigStore:
    def __init__(self, config_path: Path | None = None) -> None:
        self._config_path = config_path or default_config_path()

    def load(self) -> AppConfig:
        if not self._config_path.exists():
            return AppConfig()

        try:
            raw = json.loads(self._config_path.read_text(encoding="utf-8"))
            return self._from_dict(raw)
        except (json.JSONDecodeError, OSError, ValueError):
            return AppConfig()

    def save(self, config: AppConfig) -> None:
        self._config_path.parent.mkdir(parents=True, exist_ok=True)
        payload = asdict(config)
        self._config_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def ensure_exists(self) -> None:
        if self._config_path.exists():
            return
        self.save(AppConfig())

    def _from_dict(self, raw: dict[str, Any]) -> AppConfig:
        telegram = raw.get("telegram", {})
        profile = raw.get("job_profile", {})

        telegram_settings = TelegramSettings(
            api_id=str(telegram.get("api_id", "") or ""),
            api_hash=str(telegram.get("api_hash", "") or ""),
            phone_number=str(telegram.get("phone_number", "") or ""),
        )

        job_profile = JobProfileSettings(
            title_keywords=self._normalize_list(profile.get("title_keywords", []), lowercase=True),
            profile_keywords=self._normalize_list(profile.get("profile_keywords", []), lowercase=True),
            industry_keywords=self._normalize_list(profile.get("industry_keywords", []), lowercase=True),
            exclusion_phrases=self._normalize_list(profile.get("exclusion_phrases", []), lowercase=True),
            min_match_score=self._normalize_score(profile.get("min_match_score", 2)),
        )

        selected_chats = self._normalize_list(raw.get("selected_chats", []), lowercase=False)
        scan_depth_days = self._normalize_days(raw.get("scan_depth_days", 14))
        banned_message_links = self._normalize_list(raw.get("banned_message_links", []), lowercase=False)

        return AppConfig(
            telegram=telegram_settings,
            selected_chats=selected_chats,
            job_profile=job_profile,
            scan_depth_days=scan_depth_days,
            banned_message_links=banned_message_links,
        )

    @staticmethod
    def _normalize_list(values: Any, *, lowercase: bool) -> list[str]:
        if not isinstance(values, list):
            return []
        normalized: list[str] = []
        for item in values:
            value = str(item).strip()
            if not value:
                continue
            normalized.append(value.lower() if lowercase else value)
        return normalized

    @staticmethod
    def _normalize_score(value: Any) -> int:
        try:
            score = int(value)
        except (TypeError, ValueError):
            return 2
        return max(1, min(3, score))

    @staticmethod
    def _normalize_days(value: Any) -> int:
        try:
            days = int(value)
        except (TypeError, ValueError):
            return 14
        return max(1, min(365, days))
