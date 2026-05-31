from __future__ import annotations

from app.commands import classify_intent, COMMAND_ALIASES
from app.models import CommandIntent


def test_classify_intent_exact_commands() -> None:
    assert classify_intent("update") == CommandIntent.UPDATE
    assert classify_intent("/update") == CommandIntent.UPDATE
    assert classify_intent("emails") == CommandIntent.EMAILS
    assert classify_intent("/emails") == CommandIntent.EMAILS
    assert classify_intent("tasks") == CommandIntent.TASKS
    assert classify_intent("/tasks") == CommandIntent.TASKS
    assert classify_intent("status") == CommandIntent.STATUS
    assert classify_intent("/status") == CommandIntent.STATUS
    assert classify_intent("help") == CommandIntent.HELP
    assert classify_intent("/help") == CommandIntent.HELP
    assert classify_intent("start") == CommandIntent.HELP
    assert classify_intent("/start") == CommandIntent.HELP


def test_classify_intent_natural_language_emails() -> None:
    assert classify_intent("What are my pressing emails?") == CommandIntent.EMAILS
    assert classify_intent("Show me unread messages") == CommandIntent.EMAILS
    assert classify_intent("Check my inbox") == CommandIntent.EMAILS
    assert classify_intent("reply to emails") == CommandIntent.EMAILS


def test_classify_intent_natural_language_tasks() -> None:
    assert classify_intent("What should I focus on today?") == CommandIntent.TASKS
    assert classify_intent("Show me my Trello tasks") == CommandIntent.TASKS
    assert classify_intent("what to work on") == CommandIntent.TASKS


def test_classify_intent_natural_language_status() -> None:
    assert classify_intent("What's my status?") == CommandIntent.STATUS
    assert classify_intent("Give me a summary") == CommandIntent.STATUS
    assert classify_intent("what's up") == CommandIntent.STATUS


def test_classify_intent_unknown() -> None:
    assert classify_intent("random gibberish") == CommandIntent.UNKNOWN
    assert classify_intent("hello") == CommandIntent.UNKNOWN
    assert classify_intent("") == CommandIntent.UNKNOWN


def test_all_command_aliases_map_to_valid_intents() -> None:
    for alias, intent in COMMAND_ALIASES.items():
        assert isinstance(intent, CommandIntent)
        assert classify_intent(alias) == intent
