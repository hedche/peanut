"""One-shot entrypoint for CronJob execution.

Usage: python -m app.run
"""
from __future__ import annotations

import asyncio
import logging
import sys

import httpx

from app.config import settings
from app.gmail import get_email_context
from app.memory import load_memory, save_memory
from app.planner import plan_today
from app.scorer import score_tasks
from app.telegram import send_briefing
from app.trello import get_all_tasks

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def main() -> None:
    async with httpx.AsyncClient(timeout=30) as client:
        # 1. Fetch all tasks from Trello
        tasks = await get_all_tasks(client, settings)
        if not tasks:
            logger.warning("No tasks found on board — nothing to report")
            return

        # 2. Score deterministically
        scored = score_tasks(tasks)

        # 3. Take top N for the LLM
        top_scored = scored[: settings.top_n_for_llm]

        # 4. Load yesterday's memory
        memory = load_memory(settings.memory_file_path)

        # 5. Fetch email context (optional)
        email_context = await get_email_context(client, settings)

        # 6. Ask the LLM for today's priorities
        daily_report = await plan_today(top_scored, memory, email_context, settings)

        # 7. Save today's memory for tomorrow
        save_memory(settings.memory_file_path, daily_report)

        # 8. Send briefing to Telegram
        await send_briefing(daily_report.briefing, settings)

        logger.info(
            "Daily briefing complete — %d priorities",
            len(daily_report.top_priorities),
        )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception:
        logger.exception("Peanut run failed")
        sys.exit(1)
