from __future__ import annotations

from datetime import date

from app.models import ScoreBreakdown, ScoredTask, TrelloCard

BLOCKING_KEYWORDS = [
    "book",
    "confirm",
    "pay",
    "choose",
    "finalise",
    "finalize",
    "reserve",
    "reply",
    "respond",
    "send",
    "submit",
    "renew",
    "schedule",
    "call",
]


def _list_score(list_name: str) -> int:
    if list_name == "!! P1":
        return 50
    if list_name == "📋 P2":
        return 10
    return 0


def _due_score(due: date | None, today: date) -> int:
    if due is None:
        return 0
    days_left = (due - today).days
    if days_left < 3:
        return 40
    if days_left < 7:
        return 25
    if days_left < 14:
        return 10
    return 0


def _checklist_score(card: TrelloCard) -> int:
    if card.checklist_progress < 100.0:
        return 10
    return 0


def _blocking_score(card: TrelloCard) -> int:
    name_lower = card.name.lower()
    if any(kw in name_lower for kw in BLOCKING_KEYWORDS):
        return 15
    return 0


def score_tasks(
    tasks: list[TrelloCard],
    today: date | None = None,
) -> list[ScoredTask]:
    """Score and sort tasks by personal-assistant urgency. Returns descending by total score."""
    if today is None:
        today = date.today()

    scored: list[ScoredTask] = []
    for card in tasks:
        due_date = card.due.date() if card.due else None
        breakdown = ScoreBreakdown(
            list_score=_list_score(card.list_name),
            due_score=_due_score(due_date, today),
            checklist_score=_checklist_score(card),
            blocking_score=_blocking_score(card),
        )
        total = (
            breakdown.list_score
            + breakdown.due_score
            + breakdown.checklist_score
            + breakdown.blocking_score
        )
        scored.append(ScoredTask(card=card, breakdown=breakdown, total=total))

    scored.sort(key=lambda s: s.total, reverse=True)
    return scored
