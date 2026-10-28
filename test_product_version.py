import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from product_version import windows_version
from quota_source import CodexQuotaSource


class ProductVersionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.metadata("2.3.4-beta.9")

    def metadata(self, version):
        (self.root / "plugin.json").write_text(json.dumps({"name": "codex-pulse", "version": version}))

    def initialize(self, source):
        process = Mock(stdin=io.StringIO(), stdout=io.StringIO())
        with patch("quota_source.subprocess.Popen", return_value=process), \
                patch("quota_source.threading.Thread"), patch.object(source, "_request") as request:
            source._start()
        self.assertEqual(request.call_args.args[0], "initialize")
        return request.call_args.args[1]["clientInfo"]

    def test_windows_handshake_reads_current_metadata_instead_of_a_code_constant(self):
        with patch("quota_source.windows_version", side_effect=lambda: windows_version(self.root)):
            self.assertEqual(self.initialize(CodexQuotaSource("fixture"))["version"], "2.3.4-beta.9")
            self.metadata("2.3.5")
            self.assertEqual(self.initialize(CodexQuotaSource("fixture"))["version"], "2.3.5")

    def test_other_product_version_never_falls_back_to_windows_metadata(self):
        with patch("quota_source.windows_version", side_effect=AssertionError("wrong product source")):
            info = self.initialize(CodexQuotaSource("fixture", client_version="0.1.0-preview.5"))
        self.assertEqual(info["version"], "0.1.0-preview.5")

    def test_invalid_metadata_stops_before_starting_a_child(self):
        self.metadata(None)
        with patch("quota_source.windows_version", side_effect=lambda: windows_version(self.root)), \
                patch("quota_source.subprocess.Popen") as child:
            with self.assertRaises(ValueError):
                CodexQuotaSource("fixture")._start()
        child.assert_not_called()

    def test_missing_metadata_and_invalid_overrides_do_not_invent_versions(self):
        (self.root / "plugin.json").unlink()
        with self.assertRaises(FileNotFoundError):
            windows_version(self.root)
        for version in ("", "latest", "../0.1.0", 1):
            with self.subTest(version=version), self.assertRaises(ValueError):
                CodexQuotaSource("fixture", client_version=version)


if __name__ == "__main__":
    unittest.main()
