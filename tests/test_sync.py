import unittest

from api_sync.engine import SyncEngine, summarize
from api_sync.mock_api import MockContactAPI


def record(identifier: str, company: str = "Example") -> dict[str, object]:
    return {"external_id": identifier, "email": f"{identifier}@example.test", "first_name": "Demo", "last_name": "User", "company": company, "phone": "+49-000", "updated_at": "2026-09-01T12:00:00Z"}


class SyncTests(unittest.TestCase):
    def test_create_update_skip_and_retry(self) -> None:
        source = MockContactAPI([record("A"), record("B", "New"), record("C")])
        target = MockContactAPI([record("A"), record("B", "Old")], fail_first_attempt_for={"C"})
        events = SyncEngine(source, target).run()
        summary = summarize(events)
        self.assertEqual(summary["skipped"], 1)
        self.assertEqual(summary["updated"], 1)
        self.assertEqual(summary["created"], 1)
        self.assertEqual(summary["retried"], 1)
        self.assertEqual(summary["failed"], 0)

    def test_second_run_has_no_writes(self) -> None:
        source = MockContactAPI([record("A"), record("B")])
        target = MockContactAPI([])
        engine = SyncEngine(source, target)
        engine.run()
        replay = engine.run()
        self.assertTrue(all(event.action == "skipped" for event in replay))

    def test_invalid_record_is_rejected(self) -> None:
        bad = record("BAD")
        bad["email"] = "not-an-email"
        events = SyncEngine(MockContactAPI([bad]), MockContactAPI([])).run()
        self.assertEqual(events[0].action, "rejected")


if __name__ == "__main__":
    unittest.main()
