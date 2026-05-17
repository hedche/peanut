from datetime import date, datetime

from app.models import TrelloCard
from app.scorer import score_tasks


def _card(
    name: str = "Test task",
    list_name: str = "",
    due: datetime | None = None,
    checklist_total: int = 0,
    checklist_complete: int = 0,
) -> TrelloCard:
    return TrelloCard(
        id="abc123",
        name=name,
        list_name=list_name,
        due=due,
        checklist_total=checklist_total,
        checklist_complete=checklist_complete,
    )


TODAY = date(2026, 4, 1)


class TestListScore:
    def test_p1_gets_50(self):
        scored = score_tasks([_card(list_name="!! P1")], today=TODAY)
        assert scored[0].breakdown.list_score == 50

    def test_p2_gets_10(self):
        scored = score_tasks([_card(list_name="📋 P2")], today=TODAY)
        assert scored[0].breakdown.list_score == 10

    def test_other_list_gets_0(self):
        scored = score_tasks([_card(list_name="Someday")], today=TODAY)
        assert scored[0].breakdown.list_score == 0


class TestDueScore:
    def test_due_in_2_days(self):
        due = datetime(2026, 4, 3)
        scored = score_tasks([_card(due=due)], today=TODAY)
        assert scored[0].breakdown.due_score == 40

    def test_due_in_5_days(self):
        due = datetime(2026, 4, 6)
        scored = score_tasks([_card(due=due)], today=TODAY)
        assert scored[0].breakdown.due_score == 25

    def test_due_in_10_days(self):
        due = datetime(2026, 4, 11)
        scored = score_tasks([_card(due=due)], today=TODAY)
        assert scored[0].breakdown.due_score == 10

    def test_due_in_30_days(self):
        due = datetime(2026, 5, 1)
        scored = score_tasks([_card(due=due)], today=TODAY)
        assert scored[0].breakdown.due_score == 0

    def test_no_due_date(self):
        scored = score_tasks([_card()], today=TODAY)
        assert scored[0].breakdown.due_score == 0


class TestChecklistScore:
    def test_incomplete_checklist(self):
        scored = score_tasks(
            [_card(checklist_total=5, checklist_complete=3)], today=TODAY
        )
        assert scored[0].breakdown.checklist_score == 10

    def test_complete_checklist(self):
        scored = score_tasks(
            [_card(checklist_total=5, checklist_complete=5)], today=TODAY
        )
        assert scored[0].breakdown.checklist_score == 0

    def test_no_checklist(self):
        scored = score_tasks([_card()], today=TODAY)
        assert scored[0].breakdown.checklist_score == 0


class TestBlockingScore:
    def test_book_keyword(self):
        scored = score_tasks([_card(name="Book train tickets")], today=TODAY)
        assert scored[0].breakdown.blocking_score == 15

    def test_reply_keyword(self):
        scored = score_tasks([_card(name="Reply to accountant")], today=TODAY)
        assert scored[0].breakdown.blocking_score == 15

    def test_submit_keyword(self):
        scored = score_tasks([_card(name="Submit renewal form")], today=TODAY)
        assert scored[0].breakdown.blocking_score == 15

    def test_schedule_keyword(self):
        scored = score_tasks([_card(name="Schedule dentist")], today=TODAY)
        assert scored[0].breakdown.blocking_score == 15

    def test_no_blocking_keyword(self):
        scored = score_tasks([_card(name="Read article")], today=TODAY)
        assert scored[0].breakdown.blocking_score == 0


class TestSorting:
    def test_sorted_descending_by_total(self):
        cards = [
            _card(name="Low", list_name="Someday"),
            _card(name="High", list_name="!! P1"),
            _card(name="Mid", list_name="📋 P2"),
        ]
        scored = score_tasks(cards, today=TODAY)
        totals = [s.total for s in scored]
        assert totals == sorted(totals, reverse=True)
        assert scored[0].card.name == "High"
