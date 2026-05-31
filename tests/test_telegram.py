import json

import httpx
import pytest
import respx

from app.telegram import TELEGRAM_API, _append_sent_message, send_message


def test_append_sent_message_writes_jsonl_entry(tmp_path):
    log_path = tmp_path / "telegram_messages.jsonl"

    _append_sent_message(
        str(log_path),
        "Hello, Peanut",
        "123",
    )

    entry = json.loads(log_path.read_text(encoding="utf-8"))
    assert entry["chat_id"] == "123"
    assert entry["text"] == "Hello, Peanut"
    assert entry["timestamp"].endswith("Z")


@pytest.mark.asyncio
@respx.mock
async def test_send_message_appends_successful_send_to_log(tmp_path):
    bot_token = "bot-token"
    log_path = tmp_path / "telegram_messages.jsonl"
    route = respx.post(f"{TELEGRAM_API}/bot{bot_token}/sendMessage").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )

    await send_message(
        "Checking information.",
        "123",
        bot_token,
        str(log_path),
    )

    assert route.called
    entries = [
        json.loads(line)
        for line in log_path.read_text(encoding="utf-8").splitlines()
    ]
    assert len(entries) == 1
    assert entries[0]["chat_id"] == "123"
    assert entries[0]["text"] == "Checking information."
    assert entries[0]["timestamp"].endswith("Z")
