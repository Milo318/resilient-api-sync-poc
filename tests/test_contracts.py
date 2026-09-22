import unittest
from api_sync.autonomy import configure_and_canary_sync, ALIASES
from api_sync.engine import SyncEngine
from api_sync.mock_api import MockContactAPI, TransientAPIError


def record():
    return {
        "external_id": "A",
        "email": "a@example.test",
        "first_name": "Ada",
        "last_name": "Example",
        "company": "Demo",
        "phone": "",
        "updated_at": "2026-09-01T00:00:00Z",
    }


class ContractTests(unittest.TestCase):
    def test_no_canary_means_no_approval(self):
        mapping = {field: aliases[0] for field, aliases in ALIASES.items()}
        result = configure_and_canary_sync(list(mapping.values()), [], mapping)
        self.assertFalse(result.approved)
        self.assertTrue(result.rollback_required)

    def test_malformed_samples_do_not_escape_as_approved(self):
        mapping = {field: aliases[0] for field, aliases in ALIASES.items()}
        for samples in [[None], [{}], [{"id": "a"}]]:
            with self.subTest(samples=samples):
                self.assertFalse(
                    configure_and_canary_sync(
                        list(mapping.values()), samples, mapping
                    ).approved
                )

    def test_retry_configuration_cannot_silently_drop_records(self):
        for attempts in [0, -1, True, 1.5, 11]:
            with self.subTest(attempts=attempts), self.assertRaises(ValueError):
                SyncEngine(MockContactAPI([]), MockContactAPI([]), attempts)

    def test_input_types_and_identifiers_are_validated(self):
        for field, value in [
            ("external_id", ""),
            ("email", "@"),
            ("email", None),
            ("company", None),
            ("updated_at", "tomorrow"),
        ]:
            row = {**record(), field: value}
            with self.subTest(field=field, value=value):
                events = SyncEngine(MockContactAPI([row]), MockContactAPI([])).run()
                self.assertEqual(events[0].action, "rejected")

    def test_duplicate_target_identity_blocks_before_writing(self):
        target = MockContactAPI([record(), record()])
        with self.assertRaises(ValueError):
            SyncEngine(MockContactAPI([record()]), target).run()
        self.assertEqual(target.attempts, {})

    def test_duplicate_source_identity_is_explicitly_rejected(self):
        events = SyncEngine(
            MockContactAPI([record(), record()]), MockContactAPI([])
        ).run()
        self.assertEqual([e.action for e in events], ["created", "rejected"])

    def test_backoff_and_exhausted_retries_are_observable(self):
        class FailingAPI(MockContactAPI):
            def upsert_contact(self, record, key):
                raise TransientAPIError("temporary")

        waits = []
        result = SyncEngine(
            MockContactAPI([record()]),
            FailingAPI([]),
            sleeper=waits.append,
            retry_delay=0.5,
        ).run()
        self.assertEqual(waits, [0.5, 1.0])
        self.assertEqual((result[0].action, result[0].attempts), ("failed", 3))

    def test_write_timeout_replay_does_not_duplicate_record(self):
        class LostReceipt(MockContactAPI):
            first = True

            def upsert_contact(self, record, key):
                action = super().upsert_contact(record, key)
                if self.first:
                    self.first = False
                    raise TransientAPIError("receipt lost after write")
                return action

        target = LostReceipt([])
        result = SyncEngine(
            MockContactAPI([record()]), target, sleeper=lambda _: None
        ).run()
        self.assertEqual(result[0].action, "replayed")
        self.assertEqual(len(target.records), 1)

    def test_adapter_protocol_does_not_require_mock_inheritance(self):
        class Adapter:
            def __init__(self):
                self.rows = []

            def list_contacts(self):
                yield list(self.rows)

            def upsert_contact(self, row, key):
                self.rows.append(row)
                return "created"

        target = Adapter()
        self.assertEqual(
            SyncEngine(MockContactAPI([record()]), target).run()[0].action, "created"
        )
