from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.config import Settings
from app.email_responder import get_email_summary, get_pressing_emails
from app.models import EmailContext, GmailMessage, GmailThread


@pytest.fixture
def mock_cfg() -> Settings:
    return Settings(
        trello_api_key="tk",
        trello_api_token="tt",
        trello_board_id="bid",
        google_api_key="gk",
        telegram_bot_token="bt",
        telegram_chat_id="cid",
        gmail_refresh_token="grt",
    )


def _make_thread(subject: str, sender: str, is_unread: bool = True) -> GmailThread:
    return GmailThread(
        id=f"thread_{subject}",
        messages=[
            GmailMessage(
                id=f"msg_{subject}",
                thread_id=f"thread_{subject}",
                sender=sender,
                subject=subject,
                date=datetime.now(timezone.utc),
                snippet=f"Snippet for {subject}",
                body="",
                is_unread=is_unread,
            )
        ],
    )


@pytest.mark.asyncio
async def test_get_pressing_emails_no_gmail_config(mock_cfg: Settings) -> None:
    mock_cfg.gmail_refresh_token = ""
    mock_client = AsyncMock(spec=httpx.AsyncClient)

    result = await get_pressing_emails(mock_client, mock_cfg)

    assert "isn't configured" in result


@pytest.mark.asyncio
@patch("app.email_responder.get_email_context")
async def test_get_pressing_emails_all_caught_up(
    mock_get_ctx: AsyncMock, mock_cfg: Settings
) -> None:
    mock_get_ctx.return_value = EmailContext(
        unread_threads=[], important_threads=[], recent_threads=[]
    )
    mock_client = AsyncMock(spec=httpx.AsyncClient)

    result = await get_pressing_emails(mock_client, mock_cfg)

    assert "all caught up" in result


@pytest.mark.asyncio
@patch("app.email_responder.get_email_context")
async def test_get_pressing_emails_no_llm(
    mock_get_ctx: AsyncMock, mock_cfg: Settings
) -> None:
    mock_get_ctx.return_value = EmailContext(
        unread_threads=[
            _make_thread("Project Update", "boss@example.com"),
            _make_thread("Newsletter", "newsletter@example.com"),
        ],
        important_threads=[],
        recent_threads=[],
    )
    mock_client = AsyncMock(spec=httpx.AsyncClient)

    result = await get_pressing_emails(mock_client, mock_cfg, use_llm=False)

    assert "Unread emails" in result
    assert "Project Update" in result
    assert "boss@example.com" in result


@pytest.mark.asyncio
@patch("app.email_responder.get_email_context")
async def test_get_email_summary(mock_get_ctx: AsyncMock, mock_cfg: Settings) -> None:
    mock_get_ctx.return_value = EmailContext(
        unread_threads=[_make_thread("A", "a@b.com")],
        important_threads=[_make_thread("B", "b@c.com")],
        recent_threads=[],
    )
    mock_client = AsyncMock(spec=httpx.AsyncClient)

    result = await get_email_summary(mock_client, mock_cfg)

    assert "1 unread" in result
    assert "1 important" in result
