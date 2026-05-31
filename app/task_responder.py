from __future__ import annotations

import logging

import httpx

from app.config import Settings
from app.scorer import score_tasks
from app.trello import get_all_tasks

logger = logging.getLogger(__name__)


async def get_top_tasks(client: httpx.AsyncClient, cfg: Settings, limit: int = 5) -> str:
    """Fetch, score, and format top N tasks for Telegram."""
    tasks = await get_all_tasks(client, cfg)
    if not tasks:
        return "📋 No tasks found on your Trello board."

    scored = score_tasks(tasks)
    top = scored[:limit]

    lines = [f"📋 Top {len(top)} tasks:\n"]
    for i, st in enumerate(top, 1):
        card = st.card
        due = card.due.strftime("%b %d") if card.due else "no due date"
        assignees = ", ".join(card.assigned_to) if card.assigned_to else "unassigned"
        lines.append(
            f"{i}. *{card.name}* (list: {card.list_name}, due: {due}, assignees: {assignees})"
        )

    return "\n".join(lines)


async def get_task_summary(client: httpx.AsyncClient, cfg: Settings) -> str:
    """Quick task summary for status queries."""
    tasks = await get_all_tasks(client, cfg)
    if not tasks:
        return "📋 No tasks on your board."

    scored = score_tasks(tasks)
    urgent = [st for st in scored if st.total >= 10]
    return f"📋 {len(tasks)} total tasks, {len(urgent)} high-priority."
