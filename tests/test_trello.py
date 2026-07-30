from datetime import datetime

import pytest

from app import trello
from app.config import Settings
from app.models import TrelloCard


def _settings(**overrides) -> Settings:
    defaults = dict(
        trello_api_key="k",
        trello_api_token="t",
        trello_board_id="b",
        google_api_key="g",
        telegram_bot_token="tg",
        telegram_chat_id="123",
    )
    defaults.update(overrides)
    return Settings(**defaults)


async def test_get_all_tasks_filters_to_configured_list(monkeypatch):
    async def get_board_lists(client, cfg):
        return [
            {"id": "backlog", "name": "Backlog 📋"},
            {"id": "new", "name": "New ✨"},
            {"id": "done", "name": "Done ✅"},
        ]

    async def get_cards_for_list(client, cfg, list_id, list_name):
        return [
            TrelloCard(id=list_id, name=f"{list_name} task", list_name=list_name)
        ]

    monkeypatch.setattr(trello, "get_board_lists", get_board_lists)
    monkeypatch.setattr(trello, "get_cards_for_list", get_cards_for_list)

    tasks = await trello.get_all_tasks(None, _settings(trello_list_name="New ✨"))

    assert [task.list_name for task in tasks] == ["New ✨"]


async def test_get_all_tasks_reads_all_lists_when_filter_unset(monkeypatch):
    async def get_board_lists(client, cfg):
        return [
            {"id": "new", "name": "New ✨"},
            {"id": "done", "name": "Done ✅"},
        ]

    async def get_cards_for_list(client, cfg, list_id, list_name):
        return [
            TrelloCard(id=list_id, name=f"{list_name} task", list_name=list_name)
        ]

    monkeypatch.setattr(trello, "get_board_lists", get_board_lists)
    monkeypatch.setattr(trello, "get_cards_for_list", get_cards_for_list)

    tasks = await trello.get_all_tasks(None, _settings())

    assert [task.list_name for task in tasks] == ["New ✨", "Done ✅"]


async def test_get_all_tasks_raises_when_configured_list_missing(monkeypatch):
    async def get_board_lists(client, cfg):
        return [{"id": "done", "name": "Done ✅"}]

    monkeypatch.setattr(trello, "get_board_lists", get_board_lists)

    with pytest.raises(RuntimeError, match="Trello list 'New ✨' not found"):
        await trello.get_all_tasks(None, _settings(trello_list_name="New ✨"))


class _FakeResponse:
    def __init__(self, data):
        self._data = data

    def raise_for_status(self):
        pass

    def json(self):
        return self._data


class _FakeClient:
    def __init__(self, data):
        self._data = data

    async def get(self, url, params=None):
        return _FakeResponse(self._data)


async def test_get_cards_for_list_parses_labels():
    client = _FakeClient(
        [
            {
                "id": "c1",
                "name": "Fix boiler",
                "labels": [{"name": "P1"}, {"name": ""}, {"color": "red"}],
            }
        ]
    )

    cards = await trello.get_cards_for_list(
        client, _settings(), "backlog", "Backlog 📋"
    )

    assert cards[0].labels == ["P1"]


async def test_get_backlog_priority_cards_filters_sorts_and_truncates(monkeypatch):
    async def get_board_lists(client, cfg):
        return [
            {"id": "new", "name": "New ✨"},
            {"id": "backlog", "name": "Backlog 📋"},
        ]

    async def get_cards_for_list(client, cfg, list_id, list_name):
        return [
            TrelloCard(id="1", name="No due", labels=["p1"], list_name=list_name),
            TrelloCard(id="2", name="Not P1", due=datetime(2026, 8, 1), labels=["P2"]),
            TrelloCard(id="3", name="Later", due=datetime(2026, 8, 10), labels=["P1"]),
            TrelloCard(id="4", name="Soonest", due=datetime(2026, 8, 2), labels=["P1"]),
            TrelloCard(id="5", name="Middle", due=datetime(2026, 8, 5), labels=["P1"]),
            TrelloCard(id="6", name="Unlabelled"),
        ]

    monkeypatch.setattr(trello, "get_board_lists", get_board_lists)
    monkeypatch.setattr(trello, "get_cards_for_list", get_cards_for_list)

    cards = await trello.get_backlog_priority_cards(None, _settings())

    assert [card.name for card in cards] == ["Soonest", "Middle", "Later"]


async def test_get_backlog_priority_cards_no_due_dates_sort_last(monkeypatch):
    async def get_board_lists(client, cfg):
        return [{"id": "backlog", "name": "backlog 📋"}]

    async def get_cards_for_list(client, cfg, list_id, list_name):
        return [
            TrelloCard(id="1", name="First undated", labels=["P1"]),
            TrelloCard(id="2", name="Second undated", labels=["P1"]),
            TrelloCard(id="3", name="Dated", due=datetime(2026, 8, 2), labels=["P1"]),
        ]

    monkeypatch.setattr(trello, "get_board_lists", get_board_lists)
    monkeypatch.setattr(trello, "get_cards_for_list", get_cards_for_list)

    cards = await trello.get_backlog_priority_cards(None, _settings())

    assert [card.name for card in cards] == [
        "Dated",
        "First undated",
        "Second undated",
    ]


async def test_get_backlog_priority_cards_returns_empty_when_list_missing(
    monkeypatch,
):
    async def get_board_lists(client, cfg):
        return [{"id": "new", "name": "New ✨"}]

    monkeypatch.setattr(trello, "get_board_lists", get_board_lists)

    cards = await trello.get_backlog_priority_cards(None, _settings())

    assert cards == []
