from datetime import date

from app.memory import load_memory, save_memory
from app.models import DailyReport, PriorityItem


class TestMemory:
    def test_save_and_load_roundtrip(self, tmp_path):
        path = str(tmp_path / "memory.json")
        report = DailyReport(
            date=date(2026, 4, 14),
            top_priorities=[
                PriorityItem(
                    task="Reply to accountant", reason="Tax deadline"
                ),
                PriorityItem(
                    task="Submit renewal form", reason="Due soon"
                ),
            ],
        )
        save_memory(path, report)
        loaded = load_memory(path)

        assert loaded is not None
        assert loaded.date == date(2026, 4, 14)
        assert len(loaded.top_priorities) == 2
        assert loaded.top_priorities[0].task == "Reply to accountant"

    def test_load_missing_file_returns_none(self, tmp_path):
        path = str(tmp_path / "nonexistent.json")
        assert load_memory(path) is None

    def test_load_corrupt_file_returns_none(self, tmp_path):
        path = tmp_path / "bad.json"
        path.write_text("not valid json {{{")
        assert load_memory(str(path)) is None

    def test_carryover_flag_preserved(self, tmp_path):
        path = str(tmp_path / "memory.json")
        report = DailyReport(
            date=date(2026, 4, 14),
            top_priorities=[
                PriorityItem(
                    task="Schedule dentist",
                    reason="Carry over",
                    is_carryover=True,
                ),
            ],
        )
        save_memory(path, report)
        loaded = load_memory(path)

        assert loaded is not None
        assert loaded.top_priorities[0].is_carryover is True
