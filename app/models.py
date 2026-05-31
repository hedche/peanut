from __future__ import annotations

from datetime import date, datetime
from enum import Enum

from pydantic import BaseModel, Field


class CommandIntent(str, Enum):
    UPDATE = "update"
    EMAILS = "emails"
    TASKS = "tasks"
    STATUS = "status"
    HELP = "help"
    UNKNOWN = "unknown"


class TrelloCard(BaseModel):
    id: str
    name: str
    desc: str = ""
    due: datetime | None = None
    list_name: str = ""
    assigned_to: list[str] = Field(default_factory=list)
    checklist_total: int = 0
    checklist_complete: int = 0

    @property
    def checklist_progress(self) -> float:
        if self.checklist_total == 0:
            return 100.0
        return (self.checklist_complete / self.checklist_total) * 100.0


class ScoreBreakdown(BaseModel):
    list_score: int = 0
    due_score: int = 0
    checklist_score: int = 0
    blocking_score: int = 0


class ScoredTask(BaseModel):
    card: TrelloCard
    breakdown: ScoreBreakdown = Field(default_factory=ScoreBreakdown)
    total: int = 0


class PriorityItem(BaseModel):
    task: str
    reason: str
    is_carryover: bool = False


class AssigneePriorities(BaseModel):
    assignee: str
    priorities: list[PriorityItem]


class DailyReport(BaseModel):
    date: date
    top_priorities: list[PriorityItem]
    priorities_by_assignee: list[AssigneePriorities] = []
    briefing: str = ""
    all_scored_tasks: list[ScoredTask] = []
    email_context: EmailContext | None = None


class MemoryEntry(BaseModel):
    date: date
    top_priorities: list[PriorityItem]


class GmailMessage(BaseModel):
    """Individual email message within a Gmail thread."""

    id: str
    thread_id: str
    sender: str
    subject: str
    date: datetime
    snippet: str
    body: str = ""
    is_unread: bool = False


class GmailThread(BaseModel):
    """Conversation thread containing multiple email messages."""

    id: str
    messages: list[GmailMessage]

    @property
    def latest_message(self) -> GmailMessage | None:
        """Get the most recent message in the thread."""
        return self.messages[-1] if self.messages else None


class EmailContext(BaseModel):
    """Aggregated email context for the daily report."""

    unread_threads: list[GmailThread] = []
    important_threads: list[GmailThread] = Field(default_factory=list)
    recent_threads: list[GmailThread] = []

    @property
    def total_unread(self) -> int:
        """Total number of unread threads."""
        return len(self.unread_threads)

    @property
    def total_important_emails(self) -> int:
        """Total number of configured important sender threads."""
        return len(self.important_threads)

    @property
    def total_recent(self) -> int:
        """Total number of recent threads (excluding unread and important sender threads)."""
        return len(self.recent_threads)
