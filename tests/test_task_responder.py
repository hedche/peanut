from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.config import Settings
from app.models import ScoreBreakdown, ScoredTask, TrelloCard
from app.task_responder import get_task_summary, get_top_tasks


@pytest.fixture
def mock_cfg() -> Settings:
    return Settings(
        trello_api_key="tk",
        trello_api_token="tt",
        trello_board_id="bid",
        google_api_key="gk",
        telegram_bot_token="bt",
        telegram_chat_id="cid",
    )


def _make_card(name: str, score: int = 5) -> ScoredTask:
    return ScoredTask(
        card=TrelloCard(
            id=f"id_{name}",
            name=name,
            due=datetime.now(timezone.utc),
            list_name="Doing",
            assigned_to=["Alice"],
        ),
        breakdown=ScoreBreakdown(),
        total=score,
    )


@pytest.mark.asyncio
@patch("app.task_responder.get_all_tasks")
async def test_get_top_tasks_no_tasks(mock_get_tasks: AsyncMock, mock_cfg: Settings) -> None:
    mock_get_tasks.return_value = []
    mock_client = AsyncMock(spec=httpx.AsyncClient)

    result = await get_top_tasks(mock_client, mock_cfg)

    assert "No tasks found" in result


@pytest.mark.asyncio
@patch("app.task_responder.get_all_tasks")
@patch("app.task_responder.score_tasks")
async def test_get_top_tasks_with_tasks(
    mock_score: AsyncMock, mock_get_tasks: AsyncMock, mock_cfg: Settings
) -> None:
    card_a = TrelloCard(id="a", name="Fix bug", due=datetime.now(timezone.utc), list_name="Doing", assigned_to=["Alice"])
    card_b = TrelloCard(id="b", name="Write docs", due=datetime.now(timezone.utc), list_name="Doing", assigned_to=["Bob"])
    mock_get_tasks.return_value = [card_a, card_b]
    mock_score.return_value = [
        _make_card("Fix bug", score=15),
        _make_card("Write docs", score=8),
    ]
    mock_client = AsyncMock(spec=httpx.AsyncClient)

    result = await get_top_tasks(mock_client, mock_cfg, limit=2)

    assert "Top 2 tasks" in result
    assert "Fix bug" in result
    assert "Write docs" in result
    assert "*Fix bug*" in result  # Markdown bold


@pytest.mark.asyncio
@patch("app.task_responder.get_all_tasks")
@patch("app.task_responder.score_tasks")
async def test_get_task_summary(
    mock_score: AsyncMock, mock_get_tasks: AsyncMock, mock_cfg: Settings
) -> None:
    card_a = TrelloCard(id="a", name="Fix bug")
    card_b = TrelloCard(id="b", name="Write docs")
    card_c = TrelloCard(id="c", name="Review PR")
    mock_get_tasks.return_value = [card_a, card_b, card_c]
    mock_score.return_value = [
        _make_card("Fix bug", score=15),
        _make_card("Write docs", score=8),
        _make_card("Review PR", score=12),
    ]
    mock_client = AsyncMock(spec=httpx.AsyncClient)

    result = await get_task_summary(mock_client, mock_cfg)

    assert "3 total tasks" in result
    assert "2 high-priority" in result
