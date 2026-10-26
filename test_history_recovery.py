"""A competing local SQLite writer must not leave history permanently degraded."""
from contextlib import closing
from pathlib import Path
import queue
import sqlite3
import tempfile
import unittest

from quota_service import QuotaService


class FixtureQuotaSource:
    """An account-source contract fixture; no CLI or real account is opened."""

    def __init__(self):
        self.reads = 0

    def read(self):
        self.reads += 1
        return {
            "account_id": "fixture-account",
            "limits": {"rateLimits": {"primary": {
                "usedPercent": 20,
                "windowDurationMins": 300,
                "resetsAt": 10000,
            }}},
        }

    def close(self):
        pass


class HistoryRecoveryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / "history.sqlite3"
        self.now = 1000.0
        self.events = queue.Queue()
        self.source = FixtureQuotaSource()
        self.service = QuotaService(
            self.path, None, self.events.put, self.source, clock=lambda: self.now
        )
        self.addCleanup(self.stop_service)

    def stop_service(self):
        self.service.close()
        if self.service.thread is not None:
            self.service.thread.join(5)
            self.assertFalse(self.service.thread.is_alive())

    def test_refresh_clears_a_transient_history_error_after_writes_recover(self):
        first = self.service.read_once()
        self.assertNotIn("history_error", first)
        with closing(sqlite3.connect(self.path)) as writer:
            writer.execute("BEGIN IMMEDIATE")
            try:
                self.now += 30
                blocked = self.service.read_once()
                self.assertEqual(blocked["status"], "ready")
                self.assertIn("history_error", blocked)
            finally:
                writer.rollback()

        self.now += 30
        recovered = self.service.read_once()
        self.assertEqual(recovered["status"], "ready")
        self.assertEqual(recovered["recent"]["sample_count"], 2)
        self.assertNotIn("history_error", recovered)
        self.assertNotIn("history_error", self.events.get_nowait())
        self.events.get_nowait()  # The already asserted degraded observation.
        self.assertNotIn("history_error", self.events.get_nowait())

    def test_clear_history_removes_the_old_error_without_an_extra_account_read(self):
        self.service.start()
        self.assertNotIn("history_error", self.events.get(timeout=5))
        with closing(sqlite3.connect(self.path)) as writer:
            writer.execute("BEGIN IMMEDIATE")
            try:
                self.now += 30
                self.service.refresh()
                self.assertIn("history_error", self.events.get(timeout=10))
            finally:
                writer.rollback()

        self.service.clear_history()
        recovered = self.events.get(timeout=5)
        self.assertEqual(recovered["status"], "ready")
        self.assertEqual(recovered["recent"]["sample_count"], 0)
        self.assertNotIn("history_error", recovered)
        self.assertEqual(self.source.reads, 2)


if __name__ == "__main__":
    unittest.main()
