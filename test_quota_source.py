"""Local protocol deadlines and owned app-server shutdown, with no account access."""
import io
import queue
import subprocess
import sys
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from quota_source import CodexQuotaSource, QuotaSourceError


class DelayedReplies:
    """Transport fixture: a timed-out request replies while confirmation is pending."""

    def __init__(self, clock):
        self.clock = clock
        self.replies = [(6, {"id": 3, "result": {}}), (6, {"id": 4, "result": {}})]

    def get(self, timeout):
        delay, response = self.replies.pop(0)
        if delay > timeout:
            self.clock[0] += timeout
            raise queue.Empty
        self.clock[0] += delay
        return response


class IgnoresTermination:
    """Models a POSIX child which ignores SIGTERM; kill still releases it."""

    def __init__(self):
        self.stdin = io.StringIO()
        self.stdout = io.StringIO()
        self.alive = True

    def poll(self):
        return None if self.alive else 0

    def wait(self, timeout):
        if self.alive:
            raise subprocess.TimeoutExpired("fixture-app-server", timeout)
        return 0

    def terminate(self):
        pass

    def kill(self):
        self.alive = False


class QuotaTransportTests(unittest.TestCase):
    def test_late_prior_reply_does_not_extend_the_current_request_deadline(self):
        clock = [100.0]
        source = CodexQuotaSource(timeout=10)
        source.process = SimpleNamespace(stdin=io.StringIO())
        source.serial = 3
        source.messages = DelayedReplies(clock)
        with patch("time.monotonic", side_effect=lambda: clock[0]):
            with self.assertRaises(QuotaSourceError):
                source._request("account/read")
        self.assertLessEqual(clock[0] - 100.0, 10)

    def test_a_child_ignoring_termination_is_reaped_before_its_stream_is_closed(self):
        child = IgnoresTermination()
        source = CodexQuotaSource()
        source.process = child
        source.close()
        self.assertFalse(child.alive)
        self.assertTrue(child.stdout.closed)
        self.assertIsNone(source.process)

    def test_real_stdio_reply_and_eof_shutdown_release_the_owned_child_and_reader(self):
        program = """
import json, sys
for line in sys.stdin:
    request = json.loads(line)
    print(json.dumps({'id': request['id'], 'result': {'fixture': True}}), flush=True)
"""
        child = subprocess.Popen(
            [sys.executable, "-u", "-B", "-c", program],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, encoding="utf-8",
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        source = CodexQuotaSource(timeout=5)
        source.process = child
        reader = threading.Thread(target=source._reader, args=(child, source.messages), daemon=True)
        reader.start()
        try:
            self.assertEqual(source._request("account/read"), {"fixture": True})
        finally:
            source.close()
            reader.join(3)
        self.assertIsNotNone(child.poll())
        self.assertFalse(reader.is_alive())
        self.assertTrue(child.stdout.closed)


if __name__ == "__main__":
    unittest.main()
