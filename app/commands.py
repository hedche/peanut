from __future__ import annotations

import logging

import httpx
from fastapi import BackgroundTasks

from app.config import Settings
from app.email_responder import get_email_summary, get_pressing_emails
from app.models import CommandIntent
from app.task_responder import get_task_summary, get_top_tasks
from app.telegram import send_markdown_message, send_message

logger = logging.getLogger(__name__)

# Exact command aliases
COMMAND_ALIASES: dict[str, CommandIntent] = {
    "update": CommandIntent.UPDATE,
    "/update": CommandIntent.UPDATE,
    "emails": CommandIntent.EMAILS,
    "/emails": CommandIntent.EMAILS,
    "email": CommandIntent.EMAILS,
    "/email": CommandIntent.EMAILS,
    "tasks": CommandIntent.TASKS,
    "/tasks": CommandIntent.TASKS,
    "task": CommandIntent.TASKS,
    "/task": CommandIntent.TASKS,
    "status": CommandIntent.STATUS,
    "/status": CommandIntent.STATUS,
    "help": CommandIntent.HELP,
    "/help": CommandIntent.HELP,
    "start": CommandIntent.HELP,
    "/start": CommandIntent.HELP,
}

HELP_TEXT = """\
🥜 *Peanut Commands:*

/update — Generate full daily briefing
/emails or "pressing emails" — Check emails needing replies
/tasks or "top tasks" — List your highest-priority tasks
/status — Quick summary of emails and tasks
/help — Show this help message

You can also ask me things naturally, like:
• "What are the most pressing emails I need to reply to?"
• "What should I focus on today?"
"""


def classify_intent(text: str) -> CommandIntent:
    """Classify user intent. First try exact match, then fallback to keywords."""
    lower = text.strip().lower()

    # Exact command match
    if lower in COMMAND_ALIASES:
        return COMMAND_ALIASES[lower]

    # Keyword heuristics for common patterns (fast, no LLM call)
    if any(
        word in lower
        for word in [
            "email",
            "emails",
            "unread",
            "inbox",
            "reply",
            "message",
            "messages",
        ]
    ):
        return CommandIntent.EMAILS
    if any(
        word in lower
        for word in [
            "task",
            "tasks",
            "todo",
            "trello",
            "work",
            "focus",
        ]
    ):
        return CommandIntent.TASKS
    if any(
        word in lower
        for word in [
            "status",
            "summary",
            "overview",
            "what's up",
            "what do i have",
        ]
    ):
        return CommandIntent.STATUS

    return CommandIntent.UNKNOWN


async def dispatch_command(
    text: str,
    background_tasks: BackgroundTasks,
    cfg: Settings,
    client: httpx.AsyncClient,
) -> None:
    """Route a Telegram message to the appropriate handler."""
    intent = await classify_intent(text)
    chat_id = cfg.telegram_chat_id
    token = cfg.telegram_bot_token
    log_path = cfg.telegram_message_log_path

    if intent == CommandIntent.UPDATE:
        await send_message(
            "Checking information. We'll get back to you in a sec!",
            chat_id,
            token,
            log_path,
        )
        background_tasks.add_task(generate_and_send_report_wrapper, cfg)

    elif intent == CommandIntent.EMAILS:
        await send_message(
            "📧 Checking your emails...",
            chat_id,
            token,
            log_path,
        )
        background_tasks.add_task(
            _send_email_response, client, cfg, chat_id, token, log_path
        )

    elif intent == CommandIntent.TASKS:
        await send_message(
            "📋 Fetching your tasks...",
            chat_id,
            token,
            log_path,
        )
        background_tasks.add_task(
            _send_task_response, client, cfg, chat_id, token, log_path
        )

    elif intent == CommandIntent.STATUS:
        await send_message(
            "🥜 Getting your status...",
            chat_id,
            token,
            log_path,
        )
        background_tasks.add_task(
            _send_status_response, client, cfg, chat_id, token, log_path
        )

    elif intent == CommandIntent.HELP:
        await send_markdown_message(HELP_TEXT, chat_id, token, log_path)

    else:
        await send_message(
            "🥜 I'm not sure what you're asking. Try /help for available commands.",
            chat_id,
            token,
            log_path,
        )


# Re-export so main.py can use it for the startup/lifespan report
async def generate_and_send_report_wrapper(cfg: Settings) -> None:
    """Wrapper that imports and calls the main report generator.

    Import is deferred to avoid circular dependency between main.py and commands.py.
    """
    from app.main import generate_and_send_report

    await generate_and_send_report()


async def _send_email_response(
    client: httpx.AsyncClient,
    cfg: Settings,
    chat_id: str,
    token: str,
    log_path: str,
) -> None:
    """Background task: fetch and send pressing emails."""
    try:
        response = await get_pressing_emails(client, cfg)
        await send_markdown_message(response, chat_id, token, log_path)
    except Exception:
        logger.exception("Failed to get pressing emails")
        await send_message(
            "Sorry, I couldn't check your emails right now. Try again later.",
            chat_id,
            token,
            log_path,
        )


async def _send_task_response(
    client: httpx.AsyncClient,
    cfg: Settings,
    chat_id: str,
    token: str,
    log_path: str,
) -> None:
    """Background task: fetch and send top tasks."""
    try:
        response = await get_top_tasks(client, cfg)
        await send_markdown_message(response, chat_id, token, log_path)
    except Exception:
        logger.exception("Failed to get top tasks")
        await send_message(
            "Sorry, I couldn't fetch your tasks right now. Try again later.",
            chat_id,
            token,
            log_path,
        )


async def _send_status_response(
    client: httpx.AsyncClient,
    cfg: Settings,
    chat_id: str,
    token: str,
    log_path: str,
) -> None:
    """Background task: fetch and send quick status."""
    try:
        email_summary = await get_email_summary(client, cfg)
        task_summary = await get_task_summary(client, cfg)
        response = f"🥜 *Your Status*\n\n{email_summary}\n{task_summary}"
        await send_markdown_message(response, chat_id, token, log_path)
    except Exception:
        logger.exception("Failed to get status")
        await send_message(
            "Sorry, I couldn't get your status right now. Try again later.",
            chat_id,
            token,
            log_path,
        )
