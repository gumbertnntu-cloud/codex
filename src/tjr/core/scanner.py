from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable

from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError

from tjr.core.input_parser import parse_chat_sources_list
from tjr.core.matching import MatchResult, evaluate_message
from tjr.storage.app_paths import session_path
from tjr.storage.config_store import AppConfig

logger = logging.getLogger(__name__)
_FIXED_MIN_MATCH_SCORE = 1


@dataclass(slots=True)
class ChatMessage:
    channel: str
    published_at: datetime
    text: str
    link: str


@dataclass(slots=True)
class MatchRecord:
    channel: str
    published_at: datetime
    text: str
    link: str
    match_result: MatchResult


@dataclass(slots=True)
class ScanReport:
    scanned_chats: int
    scanned_messages: int
    matched_records: list[MatchRecord]
    canceled: bool = False


@dataclass(slots=True)
class ParsedSource:
    raw_source: str
    chat_ref: str | int
    message_id: int | None


CodeProvider = Callable[[], str | None]
PasswordProvider = Callable[[], str | None]
ProgressCallback = Callable[["ScanProgress"], None]
StopCheck = Callable[[], bool]


@dataclass(slots=True)
class ScanProgress:
    phase: str
    current_chat: str
    current_chat_index: int
    completed_chats: int
    total_chats: int
    scanned_messages: int
    matched_count: int
    latest_match: MatchRecord | None = None

_MESSAGE_LINK_RE = re.compile(r"^https?://t\.me/(?P<chat>[^/]+)/(?P<msg_id>\d+)/?$", re.IGNORECASE)
_PRIVATE_LINK_RE = re.compile(r"^https?://t\.me/c/(?P<chat_id>\d+)/(?P<msg_id>\d+)/?$", re.IGNORECASE)


def run_scan(
    config: AppConfig,
    *,
    request_code: CodeProvider | None = None,
    request_password: PasswordProvider | None = None,
    progress_callback: ProgressCallback | None = None,
    should_stop: StopCheck | None = None,
) -> ScanReport:
    state = _telegram_credentials_state(config)
    if state == "complete":
        return asyncio.run(
            _run_real_scan(
                config,
                request_code=request_code,
                request_password=request_password,
                progress_callback=progress_callback,
                should_stop=should_stop,
            )
        )
    if state == "partial":
        raise RuntimeError("Для реального скана заполните Telegram API ID, API Hash и номер телефона.")
    return _run_demo_scan(config, progress_callback=progress_callback, should_stop=should_stop)


def _telegram_credentials_state(config: AppConfig) -> str:
    tg = config.telegram
    values = [tg.api_id.strip(), tg.api_hash.strip(), tg.phone_number.strip()]
    if all(values):
        return "complete"
    if any(values):
        return "partial"
    return "empty"


async def _run_real_scan(
    config: AppConfig,
    *,
    request_code: CodeProvider | None,
    request_password: PasswordProvider | None,
    progress_callback: ProgressCallback | None,
    should_stop: StopCheck | None,
) -> ScanReport:
    now = datetime.now()
    cutoff_dt = now - timedelta(days=config.scan_depth_days)
    expanded_sources = parse_chat_sources_list(config.selected_chats)
    logger.info(
        "Source normalization | raw_count=%s | normalized_count=%s | values=%s",
        len(config.selected_chats),
        len(expanded_sources),
        ", ".join(expanded_sources),
    )
    logger.info("Date depth setup | days=%s | cutoff=%s", config.scan_depth_days, cutoff_dt.isoformat())
    sources = [_parse_source(source) for source in expanded_sources]
    banned_links = {link.strip().lower() for link in config.banned_message_links if link.strip()}
    session_path = _session_path()
    session_path.parent.mkdir(parents=True, exist_ok=True)

    api_id = int(config.telegram.api_id)
    api_hash = config.telegram.api_hash
    phone = config.telegram.phone_number

    scanned_chats = 0
    scanned_messages = 0
    matches: list[MatchRecord] = []
    canceled = False
    active_criteria_count = _active_criteria_count(config)
    effective_threshold = _effective_threshold(_FIXED_MIN_MATCH_SCORE, active_criteria_count)
    logger.info(
        "Threshold setup | mode=fixed | value=%s/3 | active=%s | effective=%s/%s",
        _FIXED_MIN_MATCH_SCORE,
        active_criteria_count,
        effective_threshold,
        max(1, active_criteria_count),
    )

    client = TelegramClient(str(session_path), api_id, api_hash)
    await client.connect()

    try:
        await _ensure_authorized(
            client,
            phone=phone,
            request_code=request_code,
            request_password=request_password,
        )

        total_chats = len(sources)
        for source_index, source in enumerate(sources, start=1):
            if _is_stop_requested(should_stop):
                canceled = True
                break
            _emit_progress(
                progress_callback,
                ScanProgress(
                    phase="chat_start",
                    current_chat=source.raw_source,
                    current_chat_index=source_index,
                    completed_chats=scanned_chats,
                    total_chats=total_chats,
                    scanned_messages=scanned_messages,
                    matched_count=len(matches),
                ),
            )
            entity, display_name = await _resolve_source_entity(client, source)
            if entity is None:
                logger.warning("Source resolve failed via Telegram API: %s", source.raw_source)
                continue

            scanned_chats += 1
            logger.info("Scanning chat: %s", display_name)
            _emit_progress(
                progress_callback,
                ScanProgress(
                    phase="chat_resolved",
                    current_chat=display_name,
                    current_chat_index=source_index,
                    completed_chats=scanned_chats - 1,
                    total_chats=total_chats,
                    scanned_messages=scanned_messages,
                    matched_count=len(matches),
                ),
            )

            try:
                messages = await _load_messages_for_source(client, entity, source, cutoff_dt, should_stop)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Source read failed via Telegram API: %s | %s", source.raw_source, exc)
                continue

            for msg in messages:
                if _is_stop_requested(should_stop):
                    canceled = True
                    break
                if msg is None:
                    continue

                text = msg.message or ""
                if not text.strip():
                    continue

                scanned_messages += 1
                published_at = msg.date.replace(tzinfo=None) if msg.date else datetime.now()
                link = _build_message_link(entity, msg.id)
                if link and link.lower() in banned_links:
                    logger.info("Message skipped by ban list | chat=%s | link=%s", display_name, link)
                    continue

                match_record = _evaluate_candidate_message(
                    channel=display_name,
                    published_at=published_at,
                    text=text,
                    link=link,
                    config=config,
                    active_criteria_count=active_criteria_count,
                    effective_threshold=effective_threshold,
                )
                if match_record is not None:
                    matches.append(match_record)
                    _emit_progress(
                        progress_callback,
                        ScanProgress(
                            phase="match_found",
                            current_chat=display_name,
                            current_chat_index=source_index,
                            completed_chats=scanned_chats - 1,
                            total_chats=total_chats,
                            scanned_messages=scanned_messages,
                            matched_count=len(matches),
                            latest_match=match_record,
                        ),
                    )

                if scanned_messages % 20 == 0:
                    _emit_progress(
                        progress_callback,
                        ScanProgress(
                            phase="message_progress",
                            current_chat=display_name,
                            current_chat_index=source_index,
                            completed_chats=scanned_chats - 1,
                            total_chats=total_chats,
                            scanned_messages=scanned_messages,
                            matched_count=len(matches),
                        ),
                    )

            _emit_progress(
                progress_callback,
                ScanProgress(
                    phase="chat_done",
                    current_chat=display_name,
                    current_chat_index=source_index,
                    completed_chats=scanned_chats,
                    total_chats=total_chats,
                    scanned_messages=scanned_messages,
                    matched_count=len(matches),
                ),
            )
            if canceled:
                break
    finally:
        await client.disconnect()

    deduped_matches = _dedupe_match_records(matches)
    removed_duplicates = len(matches) - len(deduped_matches)
    if removed_duplicates > 0:
        logger.info("Deduplicated matches | removed=%s", removed_duplicates)

    return ScanReport(
        scanned_chats=scanned_chats,
        scanned_messages=scanned_messages,
        matched_records=deduped_matches,
        canceled=canceled,
    )


async def _ensure_authorized(
    client: TelegramClient,
    *,
    phone: str,
    request_code: CodeProvider | None,
    request_password: PasswordProvider | None,
) -> None:
    if await client.is_user_authorized():
        logger.info("Telegram session authorized: reuse existing session")
        return

    logger.info("Telegram authorization required: requesting login code")
    if request_code is None:
        raise RuntimeError("Нужен код Telegram для авторизации, но окно ввода не доступно.")

    await client.send_code_request(phone)
    code = request_code()
    if not code:
        raise RuntimeError("Авторизация отменена: код не введен.")

    try:
        await client.sign_in(phone=phone, code=code)
        logger.info("Telegram authorization completed by login code")
        return
    except SessionPasswordNeededError:
        logger.info("Telegram 2FA required")
        if request_password is None:
            raise RuntimeError("Нужен пароль 2FA Telegram, но окно ввода не доступно.")

    password = request_password()
    if not password:
        raise RuntimeError("Авторизация отменена: пароль 2FA не введен.")

    await client.sign_in(password=password)
    logger.info("Telegram authorization completed with 2FA password")


async def _resolve_source_entity(client: TelegramClient, source: ParsedSource):
    try:
        entity = await client.get_entity(source.chat_ref)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Cannot resolve source '%s': %s", source.raw_source, exc)
        return None, source.raw_source

    name = getattr(entity, "title", None) or getattr(entity, "username", None) or source.raw_source
    return entity, str(name)


async def _load_messages_for_source(
    client: TelegramClient,
    entity,
    source: ParsedSource,
    cutoff_dt: datetime,
    should_stop: StopCheck | None,
):
    if source.message_id is not None:
        message = await client.get_messages(entity, ids=source.message_id)
        if message is None:
            return []
        if message.date and message.date.replace(tzinfo=None) < cutoff_dt:
            return []
        return [message]

    loaded: list = []
    async for message in client.iter_messages(entity, limit=2000):
        if _is_stop_requested(should_stop):
            break
        if message is None:
            continue
        message_dt = message.date.replace(tzinfo=None) if message.date else datetime.now()
        if message_dt < cutoff_dt:
            break
        loaded.append(message)
    return loaded


def _build_message_link(entity, message_id: int) -> str:
    username = getattr(entity, "username", None)
    if username:
        return f"https://t.me/{username}/{message_id}"

    raw_id = getattr(entity, "id", None)
    if isinstance(raw_id, int):
        return f"https://t.me/c/{raw_id}/{message_id}"
    return ""


def _session_path() -> Path:
    return session_path()


def _parse_source(source: str) -> ParsedSource:
    value = source.strip()

    private_match = _PRIVATE_LINK_RE.match(value)
    if private_match:
        internal_id = private_match.group("chat_id")
        message_id = int(private_match.group("msg_id"))
        return ParsedSource(raw_source=value, chat_ref=int(f"-100{internal_id}"), message_id=message_id)

    public_match = _MESSAGE_LINK_RE.match(value)
    if public_match:
        chat_ref = public_match.group("chat")
        message_id = int(public_match.group("msg_id"))
        return ParsedSource(raw_source=value, chat_ref=chat_ref, message_id=message_id)

    if value.startswith("https://t.me/"):
        tail = value.removeprefix("https://t.me/").strip("/")
        return ParsedSource(raw_source=value, chat_ref=tail, message_id=None)

    return ParsedSource(raw_source=value, chat_ref=value, message_id=None)


def _evaluate_candidate_message(
    *,
    channel: str,
    published_at: datetime,
    text: str,
    link: str,
    config: AppConfig,
    active_criteria_count: int,
    effective_threshold: int,
) -> MatchRecord | None:
    logger.info(
        "Scanning message | chat=%s | date=%s | link=%s | text=%s",
        channel,
        published_at.isoformat(),
        link,
        _shorten(text),
    )

    match = evaluate_message(text, config.job_profile)
    if match.excluded:
        logger.info(
            "Message excluded | chat=%s | by=%s",
            channel,
            ", ".join(match.matched_exclusion_terms),
        )
        return None

    logger.info(
        "Match metrics | chat=%s | score=%s/%s | threshold=%s/%s",
        channel,
        match.score,
        max(1, active_criteria_count),
        effective_threshold,
        max(1, active_criteria_count),
    )
    if match.score < effective_threshold:
        return None

    logger.info(
        "Match found | chat=%s | score=%s | title=%s | profile=%s | industry=%s",
        channel,
        match.score,
        ", ".join(match.matched_title_terms) or "-",
        ", ".join(match.matched_profile_terms) or "-",
        ", ".join(match.matched_industry_terms) or "-",
    )
    return MatchRecord(
        channel=channel,
        published_at=published_at,
        text=text,
        link=link,
        match_result=match,
    )


def _run_demo_scan(
    config: AppConfig,
    *,
    progress_callback: ProgressCallback | None,
    should_stop: StopCheck | None,
) -> ScanReport:
    now = datetime.now()
    cutoff_dt = now - timedelta(days=config.scan_depth_days)
    expanded_sources = parse_chat_sources_list(config.selected_chats)
    logger.info(
        "Source normalization | raw_count=%s | normalized_count=%s | values=%s",
        len(config.selected_chats),
        len(expanded_sources),
        ", ".join(expanded_sources),
    )
    logger.info("Date depth setup | days=%s | cutoff=%s", config.scan_depth_days, cutoff_dt.isoformat())
    messages = _build_demo_messages(expanded_sources)
    banned_links = {link.strip().lower() for link in config.banned_message_links if link.strip()}

    scanned_chats = 0
    scanned_messages = 0
    matches: list[MatchRecord] = []
    canceled = False
    active_criteria_count = _active_criteria_count(config)
    effective_threshold = _effective_threshold(_FIXED_MIN_MATCH_SCORE, active_criteria_count)
    logger.info(
        "Threshold setup | mode=fixed | value=%s/3 | active=%s | effective=%s/%s",
        _FIXED_MIN_MATCH_SCORE,
        active_criteria_count,
        effective_threshold,
        max(1, active_criteria_count),
    )

    total_chats = len(messages)
    for chat_index, (chat_name, chat_messages) in enumerate(messages.items(), start=1):
        if _is_stop_requested(should_stop):
            canceled = True
            break
        scanned_chats += 1
        _emit_progress(
            progress_callback,
            ScanProgress(
                phase="chat_start",
                current_chat=chat_name,
                current_chat_index=chat_index,
                completed_chats=chat_index - 1,
                total_chats=total_chats,
                scanned_messages=scanned_messages,
                matched_count=len(matches),
            ),
        )
        logger.info("Scanning chat: %s", chat_name)
        for message in chat_messages:
            if _is_stop_requested(should_stop):
                canceled = True
                break
            if message.published_at < cutoff_dt:
                continue

            if message.link and message.link.lower() in banned_links:
                logger.info("Message skipped by ban list | chat=%s | link=%s", chat_name, message.link)
                continue

            scanned_messages += 1
            logger.info(
                "Scanning message | chat=%s | date=%s | link=%s | text=%s",
                chat_name,
                message.published_at.isoformat(),
                message.link,
                _shorten(message.text),
            )

            match = evaluate_message(message.text, config.job_profile)
            if match.excluded:
                logger.info(
                    "Message excluded | chat=%s | by=%s",
                    chat_name,
                    ", ".join(match.matched_exclusion_terms),
                )
                continue
            logger.info(
                "Match metrics | chat=%s | score=%s/%s | threshold=%s/%s",
                chat_name,
                match.score,
                max(1, active_criteria_count),
                effective_threshold,
                max(1, active_criteria_count),
            )
            if match.score >= effective_threshold:
                logger.info(
                    "Match found | chat=%s | score=%s | title=%s | profile=%s | industry=%s",
                    chat_name,
                    match.score,
                    ", ".join(match.matched_title_terms) or "-",
                    ", ".join(match.matched_profile_terms) or "-",
                    ", ".join(match.matched_industry_terms) or "-",
                )
                matches.append(
                    MatchRecord(
                        channel=chat_name,
                        published_at=message.published_at,
                        text=message.text,
                        link=message.link,
                        match_result=match,
                    )
                )
                _emit_progress(
                    progress_callback,
                    ScanProgress(
                        phase="match_found",
                        current_chat=chat_name,
                        current_chat_index=chat_index,
                        completed_chats=chat_index - 1,
                        total_chats=total_chats,
                        scanned_messages=scanned_messages,
                        matched_count=len(matches),
                        latest_match=matches[-1],
                    ),
                )

            if scanned_messages % 5 == 0:
                _emit_progress(
                    progress_callback,
                    ScanProgress(
                        phase="message_progress",
                        current_chat=chat_name,
                        current_chat_index=chat_index,
                        completed_chats=chat_index - 1,
                        total_chats=total_chats,
                        scanned_messages=scanned_messages,
                        matched_count=len(matches),
                    ),
                )

        _emit_progress(
            progress_callback,
            ScanProgress(
                phase="chat_done",
                current_chat=chat_name,
                current_chat_index=chat_index,
                completed_chats=chat_index,
                total_chats=total_chats,
                scanned_messages=scanned_messages,
                matched_count=len(matches),
            ),
        )
        if canceled:
            break

    deduped_matches = _dedupe_match_records(matches)
    removed_duplicates = len(matches) - len(deduped_matches)
    if removed_duplicates > 0:
        logger.info("Deduplicated matches | removed=%s", removed_duplicates)

    return ScanReport(
        scanned_chats=scanned_chats,
        scanned_messages=scanned_messages,
        matched_records=deduped_matches,
        canceled=canceled,
    )


def _build_demo_messages(chats: list[str]) -> dict[str, list[ChatMessage]]:
    if not chats:
        return {}

    now = datetime.now()
    data: dict[str, list[ChatMessage]] = {}
    for index, chat in enumerate(chats, start=1):
        base_link = _normalize_chat_link(chat)
        data[chat] = [
            ChatMessage(
                channel=chat,
                published_at=now - timedelta(minutes=index * 3),
                text="Ищем директора по развитию в финтех проект. Нужен опыт B2B продаж.",
                link=f"{base_link}/101",
            ),
            ChatMessage(
                channel=chat,
                published_at=now - timedelta(minutes=index * 2),
                text="В команду нужен senior backend разработчик на Python и FastAPI.",
                link=f"{base_link}/102",
            ),
            ChatMessage(
                channel=chat,
                published_at=now - timedelta(minutes=index),
                text="Ищем менеджера аккаунтов в e-commerce. Офис Москва.",
                link=f"{base_link}/103",
            ),
        ]

    return data


def _normalize_chat_link(chat: str) -> str:
    if chat.startswith("http://") or chat.startswith("https://"):
        return chat.rstrip("/")
    return f"https://t.me/{chat.lstrip('@').rstrip('/')}"


def _shorten(text: str, limit: int = 180) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _active_criteria_count(config: AppConfig) -> int:
    return sum(
        [
            bool(config.job_profile.title_keywords),
            bool(config.job_profile.profile_keywords),
            bool(config.job_profile.industry_keywords),
        ]
    )


def _effective_threshold(configured_threshold: int, active_criteria_count: int) -> int:
    if active_criteria_count <= 0:
        return 1
    return max(1, min(configured_threshold, active_criteria_count))


def _dedupe_match_records(records: list[MatchRecord]) -> list[MatchRecord]:
    unique: list[MatchRecord] = []
    seen: set[str] = set()
    for record in records:
        key = _match_record_key(record)
        if key in seen:
            continue
        seen.add(key)
        unique.append(record)
    return unique


def _match_record_key(record: MatchRecord) -> str:
    link = record.link.strip().lower()
    if link:
        return f"link:{link}"
    channel = record.channel.strip().lower()
    text = record.text.strip().lower()
    return f"text:{channel}|{record.published_at.isoformat()}|{text}"


def _is_stop_requested(should_stop: StopCheck | None) -> bool:
    if should_stop is None:
        return False
    try:
        return bool(should_stop())
    except Exception:  # noqa: BLE001
        logger.exception("Stop callback failed")
        return False


def _emit_progress(progress_callback: ProgressCallback | None, progress: ScanProgress) -> None:
    if progress_callback is None:
        return
    try:
        progress_callback(progress)
    except Exception:  # noqa: BLE001
        logger.exception("Progress callback failed")
