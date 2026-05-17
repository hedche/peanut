from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

import httpx
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request, Response

from app.config import settings
from app.gmail import get_email_context
from app.memory import load_memory, save_memory
from app.metrics import metrics
from app.models import DailyReport
from app.planner import plan_today
from app.scorer import score_tasks
from app.telegram import send_briefing, send_message, set_webhook
from app.trello import get_all_tasks

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
# Suppress httpx info logs (they leak credentials in query params)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


async def generate_and_send_report() -> None:
    """Generate a new report and send it to Telegram."""
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            # 1. Fetch all tasks from Trello
            tasks = await get_all_tasks(client, settings)
            if not tasks:
                await send_message(
                    "No tasks found on the board — nothing to report.",
                    settings.telegram_chat_id,
                    settings.telegram_bot_token,
                )
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
                "On-demand briefing generated with %d priorities",
                len(daily_report.top_priorities),
            )
        except Exception:
            logger.exception("Failed to generate on-demand report")
            await send_message(
                "Sorry, I ran into an error generating the report. Please try again later.",
                settings.telegram_chat_id,
                settings.telegram_bot_token,
            )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    app.state.http_client = httpx.AsyncClient(timeout=30)

    # Set up Telegram webhook if URL is configured
    if settings.telegram_webhook_url:
        await set_webhook(settings.telegram_webhook_url, settings.telegram_bot_token)

    # Run startup report - sends Telegram message every time app starts
    # (e.g., when Flux reconciles with new image from Docker Hub)
    asyncio.create_task(generate_and_send_report())

    yield
    await app.state.http_client.aclose()


app = FastAPI(
    title="Peanut — AI Personal Assistant",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/metrics")
async def metrics_endpoint() -> Response:
    """Expose Prometheus-compatible metrics for LLM providers."""
    return Response(
        content=metrics.to_prometheus_format(),
        media_type="text/plain",
    )


@app.get("/metrics/json")
async def metrics_json_endpoint() -> dict:
    """Expose metrics in JSON format."""
    return metrics.to_json()


@app.post("/webhook/telegram")
async def telegram_webhook(request: Request, background_tasks: BackgroundTasks) -> dict[str, str]:
    """Receive Telegram webhook updates and process 'update' command."""
    try:
        data = await request.json()
        logger.debug("Received Telegram update: %s", data)

        # Extract message data
        message = data.get("message", {})
        text = message.get("text", "").strip().lower()
        chat_id = str(message.get("chat", {}).get("id", ""))

        # Only respond to messages from the configured chat
        if chat_id != settings.telegram_chat_id:
            logger.warning("Ignoring message from unknown chat: %s", chat_id)
            return {"status": "ignored"}

        # Process 'update' command
        if text == "update":
            # Send immediate acknowledgment
            await send_message(
                "Checking information. We'll get back to you in a sec!",
                chat_id,
                settings.telegram_bot_token,
            )
            # Queue report generation in background
            background_tasks.add_task(generate_and_send_report)

        return {"status": "ok"}
    except Exception:
        logger.exception("Error processing Telegram webhook")
        return {"status": "error"}


@app.get("/report")
async def report() -> DailyReport:
    """Generate today's personal-assistant briefing."""
    client: httpx.AsyncClient = app.state.http_client

    # 1. Fetch all tasks from Trello
    try:
        tasks = await get_all_tasks(client, settings)
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        if status == 401:
            raise HTTPException(
                status_code=502,
                detail="Trello API returned 401 — check TRELLO_API_KEY and TRELLO_API_TOKEN",
            )
        raise HTTPException(
            status_code=502,
            detail=f"Trello API error: {status}",
        )

    if not tasks:
        raise HTTPException(
            status_code=404,
            detail="No tasks found on the Trello board",
        )

    # 1b. Fetch Gmail context (optional - don't fail if unavailable)
    email_context = None
    if settings.gmail_refresh_token:
        try:
            email_context = await get_email_context(client, settings)
        except Exception as exc:
            logger.warning("Failed to fetch Gmail context: %s", exc)
            # Continue without email context

    # 2. Score deterministically
    scored = score_tasks(tasks)

    # 3. Take top N for the LLM
    top_scored = scored[: settings.top_n_for_llm]

    # 4. Load yesterday's memory
    memory = load_memory(settings.memory_file_path)

    # 5. Ask the LLM for today's priorities (with email context if available)
    try:
        daily_report = await plan_today(top_scored, memory, email_context, settings)
    except Exception as exc:
        logger.exception("Gemini planning failed")
        raise HTTPException(
            status_code=502,
            detail=f"Gemini API error: {exc}",
        )

    # 6. Save today's memory for tomorrow
    save_memory(settings.memory_file_path, daily_report)

    # 7. Send briefing to Telegram
    await send_briefing(daily_report.briefing, settings)

    logger.info("Report generated: %d tasks scored", len(scored))
    return daily_report
