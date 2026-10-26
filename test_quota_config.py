"""Preference compatibility and the configuration module's runtime boundary."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from quota_config import load_config


class QuotaConfigTests(unittest.TestCase):
    def test_loading_legacy_task_preferences_preserves_choices_and_source_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            original = json.dumps({
                "theme_color": "#36824b",
                "quota": {
                    "capsule": "task", "window": "secondary", "hours": 168,
                    "reminder": {"enabled": True, "source": "primary", "threshold": 0},
                },
            }).encode("utf-8")
            path.write_bytes(original)
            config = load_config(path)
            self.assertEqual((config["capsule_primary"], config["capsule_secondary"]), ("tokens", "speed"))
            self.assertEqual((config["window"], config["hours"]), ("secondary", 168))
            self.assertEqual(config["reminder"], {"enabled": True, "source": "primary", "threshold": 0})
            self.assertEqual(path.read_bytes(), original)

    def test_configuration_can_load_without_worker_database_or_native_ui(self):
        program = """
import sys
sys.path.insert(0, sys.argv[1])
from quota_config import clean_config
assert clean_config({'capsule': 'task'})['capsule_primary'] == 'tokens'
unexpected = {'quota_service', 'quota_source', 'quota_history', 'sqlite3', 'tkinter', 'threading'} & sys.modules.keys()
assert not unexpected, sorted(unexpected)
"""
        result = subprocess.run(
            [sys.executable, "-I", "-B", "-c", program, str(Path(__file__).parent)],
            capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
