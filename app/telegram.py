from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

import httpx

from app.config import Settings

if TYPE_CHECKING:
    from app.models import DailyReport

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org"
MAX_MESSAGE_LENGTH = 4096


async def send_briefing(briefing: str, cfg: Settings) -> None:
    """Send the daily briefing to Telegram. Splits long messages if needed."""
    url = f"{TELEGRAM_API}/bot{cfg.telegram_bot_token}/sendMessage"

    chunks = _split_message(briefing)
    async with httpx.AsyncClient(timeout=30) as client:
        for chunk in chunks:
            payload = {
                "chat_id": cfg.telegram_chat_id,
                "text": chunk,
            }
            try:
                resp = await client.post(url, json=payload)
                resp.raise_for_status()
                _append_sent_message(
                    cfg.telegram_message_log_path,
                    chunk,
                    cfg.telegram_chat_id,
                )
                logger.info("Telegram message sent (%d chars)", len(chunk))
            except httpx.HTTPError:
                logger.exception("Failed to send Telegram message")


async def send_message(
    text: str,
    chat_id: str,
    bot_token: str,
    message_log_path: str,
) -> None:
    """Send a plain text message to Telegram."""
    url = f"{TELEGRAM_API}/bot{bot_token}/sendMessage"
    async with httpx.AsyncClient(timeout=30) as client:
        payload = {
            "chat_id": chat_id,
            "text": text,
        }
        try:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            _append_sent_message(message_log_path, text, chat_id)
            logger.info("Telegram message sent (%d chars)", len(text))
        except httpx.HTTPError:
            logger.exception("Failed to send Telegram message")


async def set_webhook(url: str, bot_token: str) -> None:
    """Set the Telegram bot webhook URL."""
    api_url = f"{TELEGRAM_API}/bot{bot_token}/setWebhook"
    async with httpx.AsyncClient(timeout=30) as client:
        payload = {
            "url": url,
            "allowed_updates": ["message"],
        }
        try:
            resp = await client.post(api_url, json=payload)
            resp.raise_for_status()
            result = resp.json()
            if result.get("ok"):
                logger.info("Webhook set successfully: %s", url)
            else:
                logger.error("Failed to set webhook: %s", result)
        except httpx.HTTPError:
            logger.exception("Failed to set Telegram webhook")


def _split_message(text: str) -> list[str]:
    """Split a message into chunks that fit Telegram's limit."""
    if len(text) <= MAX_MESSAGE_LENGTH:
        return [text]

    chunks: list[str] = []
    while text:
        if len(text) <= MAX_MESSAGE_LENGTH:
            chunks.append(text)
            break
        # Split at last newline before the limit
        split_at = text.rfind("\n", 0, MAX_MESSAGE_LENGTH)
        if split_at == -1:
            split_at = MAX_MESSAGE_LENGTH
        chunks.append(text[:split_at])
        text = text[split_at:].lstrip("\n")
    return chunks


def _append_sent_message(
    path: str,
    text: str,
    chat_id: str,
    sent_at: datetime | None = None,
) -> None:
    try:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        timestamp = sent_at or datetime.now(timezone.utc)
        entry = {
            "timestamp": timestamp.isoformat().replace("+00:00", "Z"),
            "chat_id": chat_id,
            "text": text,
        }
        with p.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False))
            f.write("\n")
    except OSError:
        logger.exception("Failed to append Telegram message log")
