"""Documentation checks use isolated Git repositories, never personal files."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from ci.check_doc_links import check


SCRIPT = Path(__file__).with_name("ci") / "check_doc_links.py"


class DocLinkTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="pulse doc links ")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.git("init", "-q")

    def git(self, *args):
        subprocess.run(["git", *args], cwd=self.root, check=True, capture_output=True)

    def write(self, name, text="", tracked=True):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        if tracked:
            self.git("add", "--", name)
        return path

    def test_relative_images_encoded_paths_titles_and_parentheses(self):
        self.write("docs/Guide (1).md", "# Details\n")
        self.write("assets/view.png", "fixture")
        self.write("README.md", '[guide](docs/Guide%20(1).md#details "Guide title")\n'
                   '![view](assets/view.png?raw=1)\n'
                   '[literal](<docs/Guide (1).md> "Title")\n'
                   r'[escaped](docs/Guide\ \(1\).md)' + '\n')
        self.assertEqual(check(self.root), [])

    def test_reference_links_and_unicode_duplicate_headings(self):
        self.write("docs/guide.md", "# 中文 标题\n## Repeat\n## Repeat\n")
        self.write("README.md", '[read][guide]\n[guide][]\n[guide]\n[duplicate](docs/guide.md#repeat-1)\n'
                   '[guide]: docs/guide.md#%E4%B8%AD%E6%96%87-%E6%A0%87%E9%A2%98 "Guide"\n')
        self.assertEqual(check(self.root), [])

    def test_broken_markdown_anchor_fails_with_source_line(self):
        self.write("guide.md", "# Available\n")
        self.write("README.md", "# Readme\n\n[missing](guide.md#removed)\n")
        errors = check(self.root)
        self.assertEqual(len(errors), 1)
        self.assertIn("README.md:3:", errors[0])
        self.assertIn("anchor does not exist", errors[0])

    def test_deleted_link_target_fails_even_if_no_markdown_changed(self):
        target = self.write("assets/view.svg", "fixture")
        self.write("README.md", "![view](assets/view.svg)\n")
        self.assertEqual(check(self.root), [])
        target.unlink()
        self.assertIn("missing from checkout", check(self.root)[0])
        self.git("rm", "--cached", "assets/view.svg")
        self.assertIn("not tracked", check(self.root)[0])

    def test_existing_ignored_file_cannot_satisfy_a_public_link(self):
        self.write(".gitignore", "qa/\n")
        self.write("qa/report.md", "private fixture", tracked=False)
        self.write("README.md", "[report](qa/report.md)\n")
        self.assertIn("not tracked", check(self.root)[0])

    def test_untracked_markdown_is_not_scanned(self):
        self.write("README.md", "# Project\n")
        self.write("scratch.md", "[broken](missing.txt)\n", tracked=False)
        self.assertEqual(check(self.root), [])

    def test_nested_tracked_directory_is_a_valid_target_on_all_platforms(self):
        self.write("docs/nested/guide.md", "# Guide\n")
        self.write("README.md", "[directory](docs/nested/)\n")
        self.assertEqual(check(self.root), [])

    def test_fenced_inline_code_and_comments_do_not_create_false_links(self):
        self.write("README.md", '# Project\n```md\n[example](missing1)\n```\n'
                   '~~~\n[example](missing2)\n~~~\n'
                   '`[inline](missing3)` and `` `[inline](missing4)` ``\n'
                   '<!-- [comment](missing5) -->\n')
        self.assertEqual(check(self.root), [])

    def test_same_page_setext_and_explicit_anchors(self):
        self.write("README.md", '# **Start**\n[here](#start)\n[below](#next)\n'
                   'Next\n----\n<a id="custom"></a>\n[custom](#custom)\n')
        self.assertEqual(check(self.root), [])

    def test_filename_case_is_checked_even_on_case_insensitive_hosts(self):
        self.write("Guide.md", "# Guide\n")
        self.write("README.md", "[guide](guide.md)\n")
        self.assertIn("not tracked", check(self.root)[0])

    def test_path_outside_repository_is_rejected(self):
        self.write("README.md", "[outside](../outside.md)\n")
        self.assertIn("escapes repository", check(self.root)[0])

    def test_cli_reports_failure_for_a_missing_target(self):
        self.write("README.md", "[missing](missing.md)\n")
        result = subprocess.run(
            [sys.executable, "-B", str(SCRIPT), "--root", str(self.root)],
            capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("README.md:1:", result.stdout)


if __name__ == "__main__":
    unittest.main()
