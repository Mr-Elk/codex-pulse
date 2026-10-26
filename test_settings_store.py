"""Settings failures preserve the user's document and other writers' files."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import overlay_settings
from quota_backend import persist_config


class SettingsFailureTests(unittest.TestCase):
    def writers(self):
        return (
            ("strip", lambda path: overlay_settings.save(path, 15, None)),
            ("quota", lambda path: persist_config(path, {"hours": 6})),
        )

    def test_truncated_settings_are_reported_without_overwriting_the_source(self):
        for name, save in self.writers():
            with self.subTest(writer=name), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "settings.json"
                original = b'{"version":2,"theme_color":"#36824b",'
                path.write_bytes(original)
                with self.assertRaises(ValueError):
                    save(path)
                self.assertEqual(path.read_bytes(), original)
                self.assertEqual({p.name for p in path.parent.iterdir()}, {path.name})

    def test_unreadable_settings_are_not_replaced_with_defaults(self):
        for name, save in self.writers():
            with self.subTest(writer=name), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "settings.json"
                original = json.dumps({"version": 2, "custom": {"keep": True}}).encode()
                path.write_bytes(original)
                real_open = Path.open

                def denied_read(target, mode="r", *args, **kwargs):
                    if target == path and "r" in mode:
                        raise PermissionError("fixture: existing settings cannot be read")
                    return real_open(target, mode, *args, **kwargs)

                with patch.object(Path, "open", denied_read), self.assertRaises(PermissionError):
                    save(path)
                self.assertEqual(path.read_bytes(), original)

    def test_failed_replace_cleans_only_its_own_temporary_file(self):
        for name, save in self.writers():
            with self.subTest(writer=name), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "settings.json"
                original = b'{"version":2,"custom":{"keep":true}}'
                path.write_bytes(original)
                sibling = path.with_suffix(".tmp")
                sibling.write_bytes(b"another writer owns this file")
                with patch("os.replace", side_effect=PermissionError("fixture: destination is locked")):
                    with self.assertRaises(PermissionError):
                        save(path)
                self.assertEqual(path.read_bytes(), original)
                self.assertEqual(sibling.read_bytes(), b"another writer owns this file")
                self.assertEqual({p.name for p in path.parent.iterdir()}, {path.name, sibling.name})


if __name__ == "__main__":
    unittest.main()
