from __future__ import annotations

import re

_SEPARATOR_RE = re.compile(r"[\n,;]+")
_SEARCH_SEPARATOR_RE = re.compile(r"[\n,;/]+")
_PUBLIC_MESSAGE_RE = re.compile(r"^https?://t\.me/(?P<chat>[^/]+)/(?P<msg_id>\d+)/?$", re.IGNORECASE)
_PRIVATE_MESSAGE_RE = re.compile(r"^https?://t\.me/c/(?P<chat_id>\d+)/(?P<msg_id>\d+)/?$", re.IGNORECASE)
_PUBLIC_CHAT_RE = re.compile(r"^[A-Za-z0-9_]{4,}$")


def parse_user_list_input(raw: str, *, lowercase: bool) -> list[str]:
    chunks = _SEPARATOR_RE.split(raw)
    cleaned: list[str] = []
    for chunk in chunks:
        value = chunk.strip()
        if not value:
            continue
        cleaned.append(value.lower() if lowercase else value)
    return cleaned


def parse_search_terms_text(raw: str) -> list[str]:
    chunks = _SEARCH_SEPARATOR_RE.split(raw)
    cleaned: list[str] = []
    for chunk in chunks:
        value = chunk.strip().lower()
        if not value:
            continue
        cleaned.append(value)
    return cleaned


def parse_chat_sources_text(raw: str) -> list[str]:
    base = parse_user_list_input(raw, lowercase=False)
    return parse_chat_sources_list(base)


def parse_chat_sources_list(values: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        chunk = value.strip()
        if not chunk:
            continue
        for source in _split_chat_chunk(chunk):
            key = _source_dedupe_key(source)
            if key in seen:
                continue
            seen.add(key)
            normalized.append(source)
    return normalized


def _split_chat_chunk(chunk: str) -> list[str]:
    parts = [part.strip() for part in chunk.split() if part.strip()]
    if len(parts) > 1 and all(_looks_like_source(part) for part in parts):
        return parts
    return [chunk]


def _looks_like_source(value: str) -> bool:
    return (
        value.startswith("@")
        or value.startswith("http://")
        or value.startswith("https://")
        or value.startswith("t.me/")
        or value.startswith("-100")
        or value.isdigit()
    )


def _source_dedupe_key(value: str) -> str:
    source = value.strip()
    if not source:
        return ""

    private_message = _PRIVATE_MESSAGE_RE.match(source)
    if private_message:
        return f"msg:c/{private_message.group('chat_id')}/{private_message.group('msg_id')}"

    public_message = _PUBLIC_MESSAGE_RE.match(source)
    if public_message:
        chat = public_message.group("chat").lower()
        msg_id = public_message.group("msg_id")
        return f"msg:{chat}/{msg_id}"

    lowered = source.lower()
    if lowered.startswith("https://t.me/") or lowered.startswith("http://t.me/"):
        path = source.split("t.me/", 1)[1].strip("/")
        chat_ref = path.split("/", 1)[0].lstrip("@")
        if _PUBLIC_CHAT_RE.fullmatch(chat_ref):
            return f"chat:{chat_ref.lower()}"
        return f"raw:{lowered}"

    if source.startswith("@"):
        chat_ref = source[1:].strip()
        if _PUBLIC_CHAT_RE.fullmatch(chat_ref):
            return f"chat:{chat_ref.lower()}"

    if _PUBLIC_CHAT_RE.fullmatch(source):
        return f"chat:{source.lower()}"

    return f"raw:{lowered}"
