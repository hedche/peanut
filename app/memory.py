from __future__ import annotations

import json
import logging
from pathlib import Path

from app.models import DailyReport, MemoryEntry

logger = logging.getLogger(__name__)


def load_memory(path: str) -> MemoryEntry | None:
    """Load yesterday's report from disk. Returns None if missing or corrupt."""
    p = Path(path)
    if not p.exists():
        logger.info("No memory file at %s", path)
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return MemoryEntry.model_validate(data)
    except (json.JSONDecodeError, ValueError):
        logger.warning("Corrupt memory file at %s — ignoring", path)
        return None


def save_memory(path: str, report: DailyReport) -> None:
    """Persist today's top priorities for tomorrow's carryover logic."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    entry = MemoryEntry(
        date=report.date,
        top_priorities=report.top_priorities,
    )
    p.write_text(
        entry.model_dump_json(indent=2),
        encoding="utf-8",
    )
    logger.info("Memory saved to %s", path)
