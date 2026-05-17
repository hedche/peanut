from datetime import date, datetime
from unittest.mock import AsyncMock, patch

import pytest

from app.config import Settings
from app.llm_providers import LLMResponse
from app.models import (
    MemoryEntry,
    PriorityItem,
    ScoreBreakdown,
    ScoredTask,
    TrelloCard,
)
from app.planner import build_prompt, plan_today


def _settings(**overrides) -> Settings:
    defaults = dict(
        trello_api_key="k",
        trello_api_token="t",
        trello_board_id="b",
        google_api_key="g",
        telegram_bot_token="tg",
        telegram_chat_id="123",
        top_n_for_llm=10,
        top_priorities=5,
    )
    defaults.update(overrides)
    return Settings(**defaults)


def _scored_task(
    name: str,
    total: int = 50,
    assigned_to: list[str] | None = None,
) -> ScoredTask:
    card = TrelloCard(
        id="x",
        name=name,
        list_name="!! P1",
        due=datetime(2026, 4, 20),
        assigned_to=assigned_to or [],
        checklist_total=3,
        checklist_complete=1,
    )
    return ScoredTask(
        card=card,
        breakdown=ScoreBreakdown(list_score=50),
        total=total,
    )


TODAY = date(2026, 4, 14)


class TestBuildPrompt:
    def test_contains_today_and_personal_task_guidance(self):
        cfg = _settings()
        scored = [_scored_task("Reply to accountant")]
        prompt = build_prompt(scored, None, None, cfg, today=TODAY)
        assert "Today is 2026-04-14" in prompt
        assert "personal tasks" in prompt
        assert "Messages that require a reply" in prompt

    def test_contains_task_names(self):
        cfg = _settings()
        scored = [
            _scored_task("Reply to accountant"),
            _scored_task("Submit renewal form"),
        ]
        prompt = build_prompt(scored, None, None, cfg, today=TODAY)
        assert "Reply to accountant" in prompt
        assert "Submit renewal form" in prompt

    def test_includes_assignee_and_unassigned_guidance(self):
        cfg = _settings()
        scored = [
            _scored_task("Reply to accountant", assigned_to=["Alex"]),
            _scored_task("Submit renewal form"),
        ]
        prompt = build_prompt(scored, None, None, cfg, today=TODAY)
        assert "Alex" in prompt
        assert "unassigned" in prompt
        assert "EACH task" in prompt
        assert "Who is responsible" in prompt

    def test_no_carryover_message(self):
        cfg = _settings()
        prompt = build_prompt(
            [_scored_task("Task")], None, None, cfg, today=TODAY
        )
        assert "first daily briefing" in prompt

    def test_carryover_block_included(self):
        cfg = _settings()
        memory = MemoryEntry(
            date=date(2026, 4, 13),
            top_priorities=[
                PriorityItem(task="Schedule dentist", reason="Urgent"),
            ],
        )
        prompt = build_prompt(
            [_scored_task("Task")], memory, None, cfg, today=TODAY
        )
        assert "Schedule dentist" in prompt
        assert "Yesterday" in prompt


class TestPlanToday:
    @pytest.mark.asyncio
    async def test_returns_daily_report(self):
        cfg = _settings()
        scored = [_scored_task("Reply to accountant")]
        mock_response = LLMResponse(
            raw_text='[{\"task\": \"Reply to accountant\", \"reason\": \"Tax deadline\"}]',
            parsed_json=[
                {"task": "Reply to accountant", "reason": "Tax deadline"},
                {"task": "Submit renewal form", "reason": "Due soon"},
                {"task": "Schedule dentist", "reason": "Needs coordination"},
            ],
        )

        with patch(
            "app.planner.MultiProviderLLM", autospec=True
        ) as mock_llm_class:
            mock_llm = mock_llm_class.return_value
            mock_llm.generate_with_fallback = AsyncMock(
                return_value=(mock_response, "gemini", 0)
            )
            report = await plan_today(scored, None, None, cfg, today=TODAY)

        assert report.date == TODAY
        assert len(report.top_priorities) == 3
        assert report.top_priorities[0].task == "Reply to accountant"
        assert report.briefing.startswith("🥜 Daily priorities")

    @pytest.mark.asyncio
    async def test_limits_llm_priorities_to_top_configured_count(self):
        cfg = _settings(top_priorities=5)
        scored = [_scored_task(f"Task {i}") for i in range(1, 8)]
        mock_response = LLMResponse(
            raw_text="[]",
            parsed_json=[
                {"task": f"Task {i}", "reason": f"Reason {i}"}
                for i in range(1, 8)
            ],
        )

        with patch(
            "app.planner.MultiProviderLLM", autospec=True
        ) as mock_llm_class:
            mock_llm = mock_llm_class.return_value
            mock_llm.generate_with_fallback = AsyncMock(
                return_value=(mock_response, "gemini", 0)
            )
            report = await plan_today(scored, None, None, cfg, today=TODAY)

        assert len(report.top_priorities) == 5
        assert [p.task for p in report.top_priorities] == [
            "Task 1",
            "Task 2",
            "Task 3",
            "Task 4",
            "Task 5",
        ]

    async def test_detects_carryover(self):
        cfg = _settings()
        scored = [_scored_task("Reply to accountant")]
        memory = MemoryEntry(
            date=date(2026, 4, 13),
            top_priorities=[
                PriorityItem(task="Reply to accountant", reason="Urgent"),
            ],
        )
        mock_response = LLMResponse(
            raw_text='[{\"task\": \"Reply to accountant\", \"reason\": \"Still urgent\"}]',
            parsed_json=[{"task": "Reply to accountant", "reason": "Still urgent"}],
        )

        with patch(
            "app.planner.MultiProviderLLM", autospec=True
        ) as mock_llm_class:
            mock_llm = mock_llm_class.return_value
            mock_llm.generate_with_fallback = AsyncMock(
                return_value=(mock_response, "google_ai_studio", 2)
            )
            report = await plan_today(scored, memory, None, cfg, today=TODAY)

        assert report.top_priorities[0].is_carryover is True
