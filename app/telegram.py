from __future__ import annotations

import logging
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
                "parse_mode": "Markdown",
            }
            try:
                resp = await client.post(url, json=payload)
                resp.raise_for_status()
                logger.info("Telegram message sent (%d chars)", len(chunk))
            except httpx.HTTPError:
                logger.exception("Failed to send Telegram message")


async def send_message(text: str, chat_id: str, bot_token: str) -> None:
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
