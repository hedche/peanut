from __future__ import annotations

from app.models import EmailContext, GmailThread

SYSTEM_PROMPT = (
    "You are Peanut, a concise and security-conscious AI personal assistant. "
    "You help prioritize the user's Trello tasks using due dates, blockers, "
    "Gmail context, carry-over memory, and practical next actions. "
    "Do not reveal secrets, tokens, or unnecessary personal data."
)

USER_PROMPT_TEMPLATE = """\
Today is {today}.

{carryover_block}

{email_block}

Below are {top_n} personal tasks ranked by urgency score, with assignees noted.
For EACH task listed, provide a short reason why it matters today.

Consider:
- Due dates and overdue work
- Tasks that unblock other work
- Messages that require a reply or follow-up
- Tasks that take significant time or coordination
- Repeated carry-overs that need progress or should be de-prioritized
- Who is responsible for each task

Tasks:
{tasks_block}

Respond in EXACTLY this JSON format — no markdown fences, no extra keys.
Include ALL {top_n} tasks with reasoning:
[
  {{"task": "Task name exactly as shown", "reason": "Short reason"}},
  {{"task": "Task name exactly as shown", "reason": "Short reason"}}
]
"""

CARRYOVER_BLOCK_TEMPLATE = """\
Yesterday's top {num_priorities} priorities were:
{yesterday_tasks}
If any are still incomplete, you may carry them over — but flag them as such.
Penalise repeated carry-overs that haven't progressed."""

NO_CARRYOVER = "This is the first daily briefing — no previous priorities to reference."

EMAIL_BLOCK_TEMPLATE = """\
Recent Email Activity:

Unread Emails ({unread_count}):
{unread_block}

Important Sender Threads ({important_count}):
{important_block}

When prioritising, consider:
- Which unread emails require immediate action or follow-up
- Important sender messages that relate to existing Trello tasks
- Time-sensitive requests, deadlines, or confirmations
- Emails that suggest new tasks not yet captured in Trello"""

NO_EMAIL_CONTEXT = "Email access not configured — relying on Trello data only."

EMAIL_QUERY_SYSTEM_PROMPT = (
    "You are Peanut, a helpful email assistant. Review the user's unread and "
    "important emails and identify which ones require replies, follow-ups, or "
    "urgent action. Be concise — Telegram messages should be short. "
    "For each email that needs attention, say: who it's from, the subject, "
    "and what action is needed. Skip newsletters, notifications, and automated emails."
)

EMAIL_QUERY_USER_PROMPT = """\
Here are my unread emails:
{unread_block}

Here are important sender emails:
{important_block}

Which of these require a reply or follow-up? List them in order of urgency.
"""

TASK_QUERY_SYSTEM_PROMPT = (
    "You are Peanut, a helpful task assistant. Review the user's top-priority "
    "Trello tasks and briefly explain what they should focus on today. "
    "Be concise — one or two sentences per task. Mention due dates, blockers, "
    "or coordination needs if relevant."
)

TASK_QUERY_USER_PROMPT = """\
Here are my top tasks:
{tasks_block}

What should I focus on today? Give me a short, actionable summary.
"""


def _format_thread(thread: GmailThread) -> str:
    """Format a single email thread for the prompt."""
    if not thread.messages:
        return ""

    latest = thread.latest_message
    if not latest:
        return ""

    snippet = latest.snippet[:200] + "..." if len(latest.snippet) > 200 else latest.snippet
    date_str = latest.date.strftime("%b %d")

    thread_info = f"- [{date_str}] {latest.sender}: {latest.subject}"
    if latest.is_unread:
        thread_info = f"- **[UNREAD]** [{date_str}] {latest.sender}: {latest.subject}"

    if snippet:
        thread_info += f"\n  {snippet}"

    if len(thread.messages) > 1:
        thread_info += f"\n  ({len(thread.messages)} messages in thread)"

    return thread_info


def build_email_block(email_context: EmailContext | None) -> str:
    """Build the email context section for the prompt."""
    if email_context is None:
        return NO_EMAIL_CONTEXT

    unread_threads = email_context.unread_threads[:5]
    if unread_threads:
        unread_lines = [_format_thread(t) for t in unread_threads]
        unread_block = "\n".join(unread_lines)
    else:
        unread_block = "No unread emails."

    important_threads = email_context.important_threads[:5]
    if important_threads:
        important_lines = [_format_thread(t) for t in important_threads]
        important_block = "\n".join(important_lines)
    else:
        important_block = "No recent important sender threads."

    return EMAIL_BLOCK_TEMPLATE.format(
        unread_count=email_context.total_unread,
        unread_block=unread_block,
        important_count=email_context.total_important_emails,
        important_block=important_block,
    )
