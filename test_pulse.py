import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pulse import Monitor, pair_requests, timestamp

THREAD = "00000000-0000-0000-0000-000000000001"
OTHER = "00000000-0000-0000-0000-000000000002"


def tokens(output=100):
    return dict(input_tokens=1000, cached_input_tokens=800, output_tokens=output,
                reasoning_output_tokens=20, total_tokens=1000 + output)


def record(second=10, output=100, response="r1", total=None):
    return {"type": "token_usage_record", "timestamp": f"2026-10-10T00:00:{second:02d}Z",
            "payload": {"thread_id": THREAD, "turn_id": "turn1", "response_id": response,
                        "usage": tokens(output), "thread_token_usage": total or tokens(output)}}


class PairingTests(unittest.TestCase):
    def test_excludes_tool_gap_and_keeps_reasoning_inside_output(self):
        records = [{"time": 5, "turn_id": "t", "usage": tokens(100)},
                   {"time": 20, "turn_id": "t", "usage": tokens(200)}]
        starts = [{"time": 3, "turn_id": "t"}, {"time": 18, "turn_id": "t"}]
        result = pair_requests(records, starts)
        self.assertEqual(result[1]["tps"], 100)
        self.assertEqual(result[1]["duration_seconds"], 2)

    def test_missing_or_ambiguous_timing_stays_unknown(self):
        records = [{"time": 10, "turn_id": "t", "usage": tokens()}]
        self.assertIsNone(pair_requests(records, [])[0]["tps"])
        starts = [{"time": 2, "turn_id": "t"}, {"time": 3, "turn_id": "t"}]
        self.assertIsNone(pair_requests(records, starts)[0]["tps"])
        self.assertIsNone(pair_requests(records, [{"time": 2, "turn_id": "other"}])[0]["tps"])


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.path = self.root / "session.jsonl"
        self.monitor = Monitor(self.root, THREAD, self.path)
        self.write({"type": "session_meta", "payload": {"id": THREAD}},
                   {"type": "event_msg", "timestamp": "2026-10-10T00:00:00Z",
                    "payload": {"type": "task_started", "turn_id": "turn1", "model_context_window": 10000}})

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, *rows):
        with self.path.open("a", encoding="utf-8") as output:
            for row in rows:
                output.write(json.dumps(row) + "\n")

    def test_modern_legacy_and_duplicate_record_not_double_counted(self):
        row = record()
        self.write(row, {"type": "event_msg", "timestamp": row["timestamp"],
                        "payload": {"type": "token_count", "info": {
                            "total_token_usage": tokens(), "last_token_usage": tokens()}}}, row)
        result = self.monitor.snapshot()
        self.assertEqual(result["requests"], 1)
        self.assertEqual(result["usage"]["output_tokens"], 100)
        self.assertEqual(result["cache_hit_percent"], 80)
        self.assertEqual(result["context_percent_estimate"], 11)
        self.assertEqual(result["source"], "token_usage_record")
        self.assertEqual(self.monitor.snapshot()["requests"], 1)

    def test_partial_trailing_record_retried_without_loss(self):
        data = json.dumps(record()).encode()
        with self.path.open("ab") as output:
            output.write(data[:30])
        self.assertFalse(self.monitor.snapshot()["available"])
        with self.path.open("ab") as output:
            output.write(data[30:] + b"\n")
        self.assertEqual(self.monitor.snapshot()["usage"]["output_tokens"], 100)

    def test_first_request_shows_generation_before_any_usage_exists(self):
        from overlay_style import metrics
        self.monitor.starts=[{"time":timestamp("2026-10-10T00:00:05Z"),"turn_id":"turn1"}]
        with patch.object(self.monitor,"read_starts"):
            result=self.monitor.snapshot()
        self.assertFalse(result["available"])
        self.assertTrue(result.get("request_pending"))
        self.assertEqual(metrics(result)["speed"].runs[0].text,"生成中")
        self.assertEqual(metrics(result)["tokens"].runs[0].text,"—")

    def test_abort_clears_generation_and_a_later_turn_can_generate_again(self):
        self.write(record())
        self.monitor.starts=[{"time":timestamp("2026-10-10T00:00:12Z"),"turn_id":"turn1"}]
        with patch.object(self.monitor,"read_starts"):
            self.assertTrue(self.monitor.snapshot()["request_pending"])
            self.write({"type":"event_msg","timestamp":"2026-10-10T00:00:15Z",
                        "payload":{"type":"task_aborted","turn_id":"turn1"}})
            self.assertFalse(self.monitor.snapshot()["request_pending"])
            self.write({"type":"event_msg","timestamp":"2026-10-10T00:00:20Z",
                        "payload":{"type":"task_started","turn_id":"turn2"}})
            self.monitor.starts.append({"time":timestamp("2026-10-10T00:00:22Z"),"turn_id":"turn2"})
            self.assertTrue(self.monitor.snapshot()["request_pending"])

    def test_completed_turn_average_freezes(self):
        self.write(record(), {"type": "event_msg", "timestamp": "2026-10-10T00:00:20Z",
                              "payload": {"type": "task_complete", "turn_id": "turn1"}})
        first = self.monitor.snapshot(now=1791590500)
        second = self.monitor.snapshot(now=1791590600)
        self.assertEqual(first["state"], "complete")
        self.assertEqual(first["turn_average_tps"], 5)
        self.assertEqual(second["turn_average_tps"], 5)

    def test_wrong_session_refused_on_every_refresh(self):
        self.path.write_text(json.dumps({"type": "session_meta", "payload": {"id": OTHER}}) + "\n" +
                             json.dumps(record()) + "\n", encoding="utf-8")
        self.assertFalse(self.monitor.snapshot()["available"])
        self.assertFalse(self.monitor.snapshot()["available"])

    def test_no_fallback_to_a_different_conversation(self):
        folder = self.root / "sessions"
        folder.mkdir()
        (folder / f"rollout-{OTHER}.jsonl").write_text(json.dumps(record()), encoding="utf-8")
        result = Monitor(self.root, THREAD).snapshot()
        self.assertFalse(result["available"])

    def test_legacy_records_remain_supported(self):
        self.write({"type": "event_msg", "timestamp": "2026-10-10T00:00:10Z",
                    "payload": {"type": "token_count", "info": {
                        "total_token_usage": tokens(), "last_token_usage": tokens()}}})
        result = self.monitor.snapshot()
        self.assertEqual(result["source"], "token_count")
        self.assertEqual(result["usage"]["output_tokens"], 100)
        self.assertIsNone(result["latest_tps_estimate"])


if __name__ == "__main__":
    unittest.main()
