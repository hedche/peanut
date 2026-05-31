from __future__ import annotations

import logging

import httpx

from app.config import Settings
from app.gmail import get_email_context
from app.llm_providers import MultiProviderLLM
from app.prompts import (
    EMAIL_QUERY_SYSTEM_PROMPT,
    EMAIL_QUERY_USER_PROMPT,
    _format_thread,
)

logger = logging.getLogger(__name__)


async def get_pressing_emails(
    client: httpx.AsyncClient, cfg: Settings, use_llm: bool = True
) -> str:
    """Fetch emails and optionally ask LLM which need replies.

    Returns a formatted response for Telegram.
    """
    if not cfg.gmail_refresh_token:
        return "📧 Gmail isn't configured. I can't check your emails right now."

    email_context = await get_email_context(client, cfg)
    if not email_context or (
        not email_context.unread_threads and not email_context.important_threads
    ):
        return "📧 No unread or important emails right now. You're all caught up!"

    # Build prompt with top unread + important threads
    unread_threads = email_context.unread_threads[: cfg.top_emails_for_llm]
    important_threads = email_context.important_threads[: cfg.top_emails_for_llm]

    unread_block = (
        "\n".join(_format_thread(t) for t in unread_threads)
        or "No unread emails."
    )
    important_block = (
        "\n".join(_format_thread(t) for t in important_threads)
        or "No important sender emails."
    )

    if not use_llm:
        # Fast path: just list unread emails without LLM analysis
        lines = ["📧 Unread emails that might need attention:\n"]
        for t in unread_threads[:5]:
            latest = t.latest_message
            if latest:
                lines.append(f"• *{latest.subject}* from {latest.sender}")
        return "\n".join(lines)

    prompt = EMAIL_QUERY_USER_PROMPT.format(
        unread_block=unread_block,
        important_block=important_block,
    )

    # Use LLM to identify pressing emails
    llm = MultiProviderLLM(cfg)
    try:
        response, provider_name, _ = await llm.generate_with_fallback(
            prompt,
            system_instruction=EMAIL_QUERY_SYSTEM_PROMPT,
            response_mime_type="text/plain",
        )
        return response.raw_text  # type: ignore[return-value]
    except Exception as exc:
        logger.warning("LLM email analysis failed, falling back to raw list: %s", exc)
        # Fallback: just list unread emails
        lines = ["📧 Unread emails that might need attention:\n"]
        for t in unread_threads[:5]:
            latest = t.latest_message
            if latest:
                lines.append(f"• *{latest.subject}* from {latest.sender}")
        return "\n".join(lines)


async def get_email_summary(client: httpx.AsyncClient, cfg: Settings) -> str:
    """Quick email summary for status queries."""
    if not cfg.gmail_refresh_token:
        return "📧 Gmail not configured."

    email_context = await get_email_context(client, cfg)
    if not email_context:
        return "📧 No email data available."

    return (
        f"📧 {email_context.total_unread} unread, "
        f"{email_context.total_important_emails} important sender emails."
    )
