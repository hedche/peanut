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
