from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date

from app.config import Settings
from app.llm_providers import MultiProviderLLM
from app.models import (
    AssigneePriorities,
    DailyReport,
    EmailContext,
    MemoryEntry,
    PriorityItem,
    ScoredTask,
)
from app.prompts import (
    CARRYOVER_BLOCK_TEMPLATE,
    NO_CARRYOVER,
    USER_PROMPT_TEMPLATE,
    build_email_block,
)

logger = logging.getLogger(__name__)


def _build_tasks_block(scored: list[ScoredTask]) -> str:
    lines: list[str] = []
    for i, st in enumerate(scored, 1):
        card = st.card
        due_str = card.due.strftime("%Y-%m-%d") if card.due else "no due date"
        checklist = (
            f"{card.checklist_complete}/{card.checklist_total}"
            if card.checklist_total > 0
            else "no checklist"
        )
        assignees = ", ".join(card.assigned_to) if card.assigned_to else "unassigned"
        lines.append(
            f"{i}. [{st.total}pts] {card.name} "
            f"(list: {card.list_name}, assignees: {assignees}, due: {due_str}, "
            f"checklist: {checklist})"
        )
    return "\n".join(lines)


def _group_by_assignee(
    scored: list[ScoredTask],
) -> tuple[dict[str, list[ScoredTask]], list[ScoredTask]]:
    """Group scored tasks by assignee. Cards with multiple assignees appear in each group."""
    by_assignee: dict[str, list[ScoredTask]] = defaultdict(list)
    unassigned: list[ScoredTask] = []
    for st in scored:
        if st.card.assigned_to:
            for name in st.card.assigned_to:
                by_assignee[name].append(st)
        else:
            unassigned.append(st)
    return dict(by_assignee), unassigned


def _build_carryover_block(
    memory: MemoryEntry | None, num_priorities: int
) -> str:
    if memory is None:
        return NO_CARRYOVER
    items = "\n".join(
        f"  - {p.task}: {p.reason}" for p in memory.top_priorities
    )
    return CARRYOVER_BLOCK_TEMPLATE.format(
        num_priorities=num_priorities,
        yesterday_tasks=items,
    )


def build_prompt(
    scored: list[ScoredTask],
    memory: MemoryEntry | None,
    email_context: EmailContext | None,
    cfg: Settings,
    today: date | None = None,
) -> str:
    if today is None:
        today = date.today()

    tasks_block = _build_tasks_block(scored)
    carryover_block = _build_carryover_block(memory, cfg.top_priorities)
    email_block = build_email_block(email_context)

    return USER_PROMPT_TEMPLATE.format(
        today=today.isoformat(),
        top_n=len(scored),
        num_priorities=cfg.top_priorities,
        tasks_block=tasks_block,
        carryover_block=carryover_block,
        email_block=email_block,
    )


def _format_briefing(
    priorities: list[PriorityItem],
    title: str = "Daily priorities",
    provider_name: str = "",
    assignee_priorities: list[AssigneePriorities] | None = None,
    all_scored: list[ScoredTask] | None = None,
) -> str:
    scored_lookup: dict[str, ScoredTask] = {}
    if all_scored:
        scored_lookup = {st.card.name.lower(): st for st in all_scored}

    def _score_str(task_name: str) -> str:
        st = scored_lookup.get(task_name.lower())
        if not st:
            return ""
        bd = st.breakdown
        return (
            f" [{st.total}pts L:{bd.list_score} D:{bd.due_score}"
            f" C:{bd.checklist_score} B:{bd.blocking_score}]"
        )

    lines = [f"🥜 {title}"]

    if assignee_priorities:
        for ap in assignee_priorities:
            lines.append(f"\n📋 {ap.assignee}:\n")
            for i, p in enumerate(ap.priorities, 1):
                lines.append(
                    f"{i}. {p.task}{_score_str(p.task)}"
                )
    else:
        lines.append("\nTop priorities for today:\n")
        for i, p in enumerate(priorities, 1):
            lines.append(
                f"{i}. {p.task}{_score_str(p.task)}"
            )
    return "\n".join(lines)


def _detect_carryovers(
    items: list[dict[str, str]], memory: MemoryEntry | None
) -> list[PriorityItem]:
    yesterday_names: set[str] = set()
    if memory:
        yesterday_names = {p.task.lower() for p in memory.top_priorities}

    priorities: list[PriorityItem] = []
    for item in items:
        task_name = item.get("task", "")
        is_carryover = task_name.lower() in yesterday_names
        priorities.append(
            PriorityItem(
                task=task_name,
                reason=item.get("reason", ""),
                is_carryover=is_carryover,
            )
        )
    return priorities


async def plan_today(
    scored: list[ScoredTask],
    memory: MemoryEntry | None,
    email_context: EmailContext | None,
    cfg: Settings,
    today: date | None = None,
) -> DailyReport:
    """Run the full planning pipeline: build prompt, call LLM with fallback, format report."""
    if today is None:
        today = date.today()

    # Group tasks by assignee
    by_assignee, unassigned = _group_by_assignee(scored)
    has_assignees = bool(by_assignee)

    # Collect tasks for LLM: per-assignee tops + unassigned tops (deduped)
    if has_assignees:
        llm_tasks: list[ScoredTask] = []
        seen_ids: set[str] = set()
        for name in sorted(by_assignee):
            for st in by_assignee[name][: cfg.priorities_per_assignee]:
                if st.card.id not in seen_ids:
                    seen_ids.add(st.card.id)
                    llm_tasks.append(st)
        for st in unassigned[: cfg.priorities_unassigned]:
            if st.card.id not in seen_ids:
                seen_ids.add(st.card.id)
                llm_tasks.append(st)
    else:
        llm_tasks = scored

    # Call LLM for reasoning on all selected tasks
    llm = MultiProviderLLM(cfg)
    llm_reasons: dict[str, str] = {}
    provider_name = "deterministic_fallback"
    retry_count = 0

    try:
        prompt = build_prompt(llm_tasks, memory, email_context, cfg, today)
        logger.info("Sending %d tasks to LLM for planning", len(llm_tasks))
        response, provider_name, retry_count = await llm.generate_with_fallback(prompt)
        for item in response.parsed_json:
            llm_reasons[item.get("task", "").lower()] = item.get("reason", "")
    except Exception as exc:
        logger.warning("LLM failed (%s), falling back to deterministic priorities", exc)

    # Build per-assignee priorities with LLM reasoning
    assignee_priorities: list[AssigneePriorities] = []
    flat_priorities: list[PriorityItem] = []

    if has_assignees:
        for name in sorted(by_assignee):
            tasks = by_assignee[name][: cfg.priorities_per_assignee]
            items = _detect_carryovers(
                [
                    {
                        "task": st.card.name,
                        "reason": llm_reasons.get(
                            st.card.name.lower(),
                            f"Top scored task ({st.total} pts) for {name}",
                        ),
                    }
                    for st in tasks
                ],
                memory,
            )
            assignee_priorities.append(
                AssigneePriorities(assignee=name, priorities=items)
            )
            flat_priorities.extend(items)

        # Unassigned group
        unassigned_top = unassigned[: cfg.priorities_unassigned]
        if unassigned_top:
            items = _detect_carryovers(
                [
                    {
                        "task": st.card.name,
                        "reason": llm_reasons.get(
                            st.card.name.lower(),
                            f"Top scored unassigned task ({st.total} pts)",
                        ),
                    }
                    for st in unassigned_top
                ],
                memory,
            )
            assignee_priorities.append(
                AssigneePriorities(assignee="Unassigned", priorities=items)
            )
            flat_priorities.extend(items)
    else:
        # No assignees — flat list
        if llm_reasons:
            flat_priorities = _detect_carryovers(
                response.parsed_json[: cfg.top_priorities], memory
            )
        else:
            top_tasks = scored[: cfg.top_priorities]
            flat_priorities = [
                PriorityItem(
                    task=st.card.name,
                    reason=f"Highest scored task ({st.total} points) - LLM unavailable",
                    is_carryover=False,
                )
                for st in top_tasks
            ]

    briefing = _format_briefing(
        flat_priorities,
        cfg.briefing_title,
        provider_name,
        assignee_priorities or None,
        scored,
    )

    # Log summary
    email_summary = ""
    if email_context:
        email_summary = f" emails=[{email_context.total_unread} unread, {email_context.total_important_emails} important]"

    assignee_summary = ""
    if has_assignees:
        assignee_summary = f" assignees={len(by_assignee)} unassigned={len(unassigned)}"

    logger.info(
        "Planning complete: provider=%s retries=%d tasks=%d priorities=%d%s%s",
        provider_name,
        retry_count,
        len(scored),
        len(flat_priorities),
        email_summary,
        assignee_summary,
    )

    return DailyReport(
        date=today,
        top_priorities=flat_priorities,
        priorities_by_assignee=assignee_priorities,
        briefing=briefing,
        all_scored_tasks=scored,
        email_context=email_context,
    )
