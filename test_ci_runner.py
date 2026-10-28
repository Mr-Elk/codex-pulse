"""CI failures must remain visible in both the process status and saved logs."""
from contextlib import redirect_stdout
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from ci.run_windows_tests import run_ci, run_logged


class CILogTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="pulse ci logs ")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.log = self.root / "result.log"

    def execute(self, command, timeout=10):
        output = io.StringIO()
        with redirect_stdout(output):
            code = run_logged(command, self.log, cwd=self.root, timeout=timeout)
        return code, output.getvalue(), self.log.read_text(encoding="utf-8")

    def test_failed_child_keeps_both_output_streams_and_exit_code(self):
        code, output, log = self.execute([
            sys.executable, "-X", "utf8", "-c",
            "import sys; print('stdout'); print('错误详情', file=sys.stderr); sys.exit(7)",
        ])
        self.assertEqual(code, 7)
        for expected in ("stdout", "错误详情"):
            self.assertIn(expected, log)
            self.assertIn(expected, output)

    def test_success_is_logged_without_changing_its_status(self):
        code, output, log = self.execute([sys.executable, "-c", "print('passed')"])
        self.assertEqual(code, 0)
        self.assertIn("passed", log)
        self.assertIn("exit code: 0", output)

    def test_missing_program_records_start_failure(self):
        code, _, log = self.execute([str(self.root / "missing-program")])
        self.assertEqual(code, 127)
        self.assertIn("could not start", log)

    def test_stalled_child_is_bounded_and_reported_as_failure(self):
        code, _, log = self.execute(
            [sys.executable, "-c", "import time; time.sleep(30)"], timeout=0.2,
        )
        self.assertEqual(code, 124)
        self.assertIn("timed out", log)

    def test_failed_preflight_prevents_regression_from_starting(self):
        with patch("ci.run_windows_tests.run_logged", return_value=9) as child:
            self.assertEqual(run_ci(self.root), 9)
        self.assertEqual(child.call_count, 1)

    def test_regression_failure_is_not_overwritten_by_logging(self):
        with patch("ci.run_windows_tests.run_logged", side_effect=[0, 7]):
            self.assertEqual(run_ci(self.root), 7)


if __name__ == "__main__":
    unittest.main()
