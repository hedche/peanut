from __future__ import annotations

import logging
from datetime import datetime

import httpx

from app.config import Settings
from app.models import TrelloCard

logger = logging.getLogger(__name__)

BASE_URL = "https://api.trello.com/1"


async def _auth_params(cfg: Settings) -> dict[str, str]:
    return {"key": cfg.trello_api_key, "token": cfg.trello_api_token}


async def get_board_lists(
    client: httpx.AsyncClient, cfg: Settings
) -> list[dict[str, str]]:
    """Fetch all lists on the board. Returns list of {id, name}."""
    params = await _auth_params(cfg)
    resp = await client.get(
        f"{BASE_URL}/boards/{cfg.trello_board_id}/lists",
        params=params,
    )
    resp.raise_for_status()
    return [{"id": lst["id"], "name": lst["name"]} for lst in resp.json()]


async def get_cards_for_list(
    client: httpx.AsyncClient,
    cfg: Settings,
    list_id: str,
    list_name: str,
) -> list[TrelloCard]:
    """Fetch all open cards in a list, including checklist data."""
    params = {
        **(await _auth_params(cfg)),
        "checklists": "all",
        "members": "true",
        "member_fields": "fullName,username",
    }
    resp = await client.get(
        f"{BASE_URL}/lists/{list_id}/cards",
        params=params,
    )
    resp.raise_for_status()

    cards: list[TrelloCard] = []
    for raw in resp.json():
        checklist_total = 0
        checklist_complete = 0
        for cl in raw.get("checklists", []):
            for item in cl.get("checkItems", []):
                checklist_total += 1
                if item.get("state") == "complete":
                    checklist_complete += 1

        cards.append(
            TrelloCard(
                id=raw["id"],
                name=raw["name"],
                desc=raw.get("desc", ""),
                due=raw.get("due"),
                list_name=list_name,
                labels=[
                    label["name"]
                    for label in raw.get("labels", [])
                    if label.get("name")
                ],
                assigned_to=[
                    member.get("fullName") or member.get("username", "")
                    for member in raw.get("members", [])
                    if member.get("fullName") or member.get("username")
                ],
                checklist_total=checklist_total,
                checklist_complete=checklist_complete,
            )
        )
    return cards


def _cards_with_label(cards: list[TrelloCard], label: str) -> list[TrelloCard]:
    wanted = label.casefold()
    return [
        card
        for card in cards
        if any(name.casefold() == wanted for name in card.labels)
    ]


async def get_backlog_priority_cards(
    client: httpx.AsyncClient, cfg: Settings
) -> tuple[list[TrelloCard], str]:
    """Fetch the top backlog cards carrying the priority label.

    Returns the first `backlog_top_n` cards from the backlog list that have the
    configured label, soonest due date first (cards without a due date last,
    keeping Trello list order as tie-break), plus the label that matched. When
    no card has the primary label, falls back to `backlog_fallback_label_name`.
    Returns ([], primary label) instead of raising when the list is missing so
    the main briefing is never blocked.
    """
    lists = await get_board_lists(client, cfg)
    target = next(
        (
            lst
            for lst in lists
            if lst["name"].casefold() == cfg.backlog_list_name.casefold()
        ),
        None,
    )
    if target is None:
        logger.warning(
            "Backlog list %r not found on board %s — skipping backlog section",
            cfg.backlog_list_name,
            cfg.trello_board_id,
        )
        return [], cfg.backlog_label_name

    cards = await get_cards_for_list(client, cfg, target["id"], target["name"])
    label_used = cfg.backlog_label_name
    matching = _cards_with_label(cards, cfg.backlog_label_name)
    if not matching and cfg.backlog_fallback_label_name:
        label_used = cfg.backlog_fallback_label_name
        matching = _cards_with_label(cards, cfg.backlog_fallback_label_name)
    matching.sort(key=lambda card: (card.due is None, card.due or datetime.min))
    top = matching[: cfg.backlog_top_n]
    logger.info(
        "Backlog %s: %d cards, %d with label %r, taking top %d",
        target["name"],
        len(cards),
        len(matching),
        label_used,
        len(top),
    )
    return top, label_used


async def get_all_tasks(
    client: httpx.AsyncClient, cfg: Settings
) -> list[TrelloCard]:
    """Fetch open cards from the configured board/list."""
    lists = await get_board_lists(client, cfg)
    logger.info("Found %d lists on board %s", len(lists), cfg.trello_board_id)

    if cfg.trello_list_name:
        lists = [lst for lst in lists if lst["name"] == cfg.trello_list_name]
        if not lists:
            raise RuntimeError(f"Trello list {cfg.trello_list_name!r} not found")
        logger.info("Filtering Trello cards to list: %s", cfg.trello_list_name)

    all_cards: list[TrelloCard] = []
    for lst in lists:
        cards = await get_cards_for_list(client, cfg, lst["id"], lst["name"])
        logger.info("  %s: %d cards", lst["name"], len(cards))
        all_cards.extend(cards)

    logger.info("Total cards fetched: %d", len(all_cards))
    return all_cards
