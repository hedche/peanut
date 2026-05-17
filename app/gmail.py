from __future__ import annotations

import base64
import email.utils
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from app.config import Settings
from app.models import EmailContext, GmailMessage, GmailThread

logger = logging.getLogger(__name__)

GMAIL_API_BASE = "https://gmail.googleapis.com/gmail/v1"


async def _refresh_access_token(client: httpx.AsyncClient, cfg: Settings) -> str:
    """Exchange refresh token for a new access token."""
    if not all([cfg.gmail_client_id, cfg.gmail_client_secret, cfg.gmail_refresh_token]):
        raise ValueError("Missing Gmail OAuth credentials")

    resp = await client.post(
        "https://oauth2.googleapis.com/token",
        data={
            "client_id": cfg.gmail_client_id,
            "client_secret": cfg.gmail_client_secret,
            "refresh_token": cfg.gmail_refresh_token,
            "grant_type": "refresh_token",
        },
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


async def _gmail_request(
    client: httpx.AsyncClient,
    cfg: Settings,
    method: str,
    endpoint: str,
    **kwargs: Any,
) -> Any:
    """Make an authenticated Gmail API request."""
    access_token = await _refresh_access_token(client, cfg)
    headers = kwargs.pop("headers", {})
    headers["Authorization"] = f"Bearer {access_token}"

    url = f"{GMAIL_API_BASE}/{endpoint}"
    resp = await client.request(method, url, headers=headers, **kwargs)
    resp.raise_for_status()
    return resp.json()


def _parse_email_date(date_str: str) -> datetime:
    """Parse email date string to datetime (handles various formats)."""
    try:
        # Try RFC 2822 parsing first
        parsed = email.utils.parsedate_tz(date_str)
        if parsed:
            timestamp = email.utils.mktime_tz(parsed)
            return datetime.fromtimestamp(timestamp, tz=timezone.utc)
    except Exception:
        pass

    # Fallback to ISO format parsing
    try:
        return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    except Exception:
        pass

    # Last resort: return current time
    return datetime.now(timezone.utc)


def _extract_header(headers: list[dict[str, str]], name: str) -> str:
    """Extract a header value from Gmail headers list."""
    for header in headers:
        if header.get("name", "").lower() == name.lower():
            return header.get("value", "")
    return ""


def _decode_body(payload: dict[str, Any]) -> str:
    """Extract and decode the body text from a Gmail message payload."""
    body_text = ""

    # Try to get body from current payload
    if "body" in payload and "data" in payload["body"]:
        data = payload["body"]["data"]
        try:
            body_text = base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
        except Exception:
            pass

    # If multipart, look for text/plain or text/html parts
    if not body_text and "parts" in payload:
        for part in payload["parts"]:
            mime_type = part.get("mimeType", "")
            if mime_type == "text/plain" and "body" in part and "data" in part["body"]:
                try:
                    data = part["body"]["data"]
                    body_text = base64.urlsafe_b64decode(data).decode(
                        "utf-8", errors="ignore"
                    )
                    break
                except Exception:
                    continue
            elif mime_type == "text/html" and "body" in part and "data" in part["body"]:
                try:
                    data = part["body"]["data"]
                    html = base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
                    # Simple HTML to text (could use a library, but keeping it simple)
                    import re

                    text = re.sub(r"<[^>]+>", " ", html)
                    text = re.sub(r"\s+", " ", text).strip()
                    body_text = text
                    break
                except Exception:
                    continue

    return body_text[:2000]  # Limit body size


async def _fetch_message(
    client: httpx.AsyncClient,
    cfg: Settings,
    message_id: str,
) -> GmailMessage | None:
    """Fetch full message details from Gmail API."""
    try:
        data = await _gmail_request(
            client,
            cfg,
            "GET",
            f"users/me/messages/{message_id}",
            params={"format": "full"},
        )

        payload = data.get("payload", {})
        headers = payload.get("headers", [])

        # Extract fields
        sender = _extract_header(headers, "From")
        subject = _extract_header(headers, "Subject")
        date_str = _extract_header(headers, "Date")

        # Parse date
        date = _parse_email_date(date_str) if date_str else datetime.now(timezone.utc)

        # Check unread label
        labels = data.get("labelIds", [])
        is_unread = "UNREAD" in labels

        # Decode body
        body = _decode_body(payload)

        return GmailMessage(
            id=message_id,
            thread_id=data.get("threadId", ""),
            sender=sender,
            subject=subject,
            date=date,
            snippet=data.get("snippet", ""),
            body=body,
            is_unread=is_unread,
        )
    except Exception as exc:
        logger.warning("Failed to fetch message %s: %s", message_id, exc)
        return None


async def _fetch_thread_messages(
    client: httpx.AsyncClient,
    cfg: Settings,
    thread_id: str,
) -> GmailThread | None:
    """Fetch all messages in a thread."""
    try:
        data = await _gmail_request(
            client, cfg, "GET", f"users/me/threads/{thread_id}"
        )

        messages = []
        for msg_ref in data.get("messages", []):
            msg = await _fetch_message(client, cfg, msg_ref["id"])
            if msg:
                messages.append(msg)

        # Sort by date
        messages.sort(key=lambda m: m.date)

        return GmailThread(id=thread_id, messages=messages)
    except Exception as exc:
        logger.warning("Failed to fetch thread %s: %s", thread_id, exc)
        return None


async def search_threads(
    client: httpx.AsyncClient,
    cfg: Settings,
    query: str,
    max_results: int = 20,
) -> list[GmailThread]:
    """Search for threads matching the query."""
    try:
        data = await _gmail_request(
            client,
            cfg,
            "GET",
            "users/me/threads",
            params={"q": query, "maxResults": max_results},
        )

        threads = []
        for thread_ref in data.get("threads", []):
            thread = await _fetch_thread_messages(client, cfg, thread_ref["id"])
            if thread and thread.messages:
                threads.append(thread)

        return threads
    except Exception as exc:
        logger.error("Failed to search threads with query '%s': %s", query, exc)
        return []


async def fetch_unread_threads(
    client: httpx.AsyncClient,
    cfg: Settings,
    max_results: int = 20,
) -> list[GmailThread]:
    """Fetch threads with unread messages."""
    threads = await search_threads(client, cfg, "is:unread", max_results)
    logger.info("Fetched %d unread threads", len(threads))
    return threads


async def fetch_important_threads(
    client: httpx.AsyncClient,
    cfg: Settings,
    max_results: int = 20,
) -> list[GmailThread]:
    """Fetch threads from configured important sender email addresses."""
    if not cfg.gmail_sender_emails:
        return []

    # Build OR query for all sender emails
    senders = [s.strip() for s in cfg.gmail_sender_emails.split(",") if s.strip()]
    if not senders:
        return []

    # Create query: from:(sender1 OR sender2 OR sender3)
    sender_query = " OR ".join([f"from:{sender}" for sender in senders])
    query = f"from:({sender_query})"

    threads = await search_threads(client, cfg, query, max_results)
    logger.info("Fetched %d important sender threads from %d senders", len(threads), len(senders))
    return threads


async def fetch_recent_threads(
    client: httpx.AsyncClient,
    cfg: Settings,
    days: int = 14,
    max_results: int = 20,
) -> list[GmailThread]:
    """Fetch threads from the last N days, excluding unread and important sender emails."""
    cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)
    date_str = cutoff_date.strftime("%Y/%m/%d")

    # Query for recent emails, excluding those already in unread/important sender sets
    query = f"after:{date_str} -is:unread"

    threads = await search_threads(client, cfg, query, max_results)
    logger.info("Fetched %d recent threads (last %d days)", len(threads), days)
    return threads


async def get_email_context(
    client: httpx.AsyncClient,
    cfg: Settings,
) -> EmailContext | None:
    """Fetch comprehensive email context for the daily report."""
    if not cfg.gmail_refresh_token:
        logger.info("Gmail not configured, skipping email context")
        return None

    logger.info("Fetching email context...")

    # Fetch from multiple sources
    unread = await fetch_unread_threads(client, cfg, max_results=15)
    important = await fetch_important_threads(client, cfg, max_results=15)
    recent = await fetch_recent_threads(client, cfg, days=14, max_results=10)

    # Deduplicate: don't include threads in recent that are already in unread or important
    unread_thread_ids = {t.id for t in unread}
    important_thread_ids = {t.id for t in important}

    filtered_recent = [
        t
        for t in recent
        if t.id not in unread_thread_ids and t.id not in important_thread_ids
    ]

    context = EmailContext(
        unread_threads=unread,
        important_threads=important,
        recent_threads=filtered_recent,
    )

    logger.info(
        "Email context: %d unread, %d important, %d recent",
        context.total_unread,
        context.total_important_emails,
        context.total_recent,
    )

    return context
