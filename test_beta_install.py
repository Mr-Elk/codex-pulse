import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import manage
from release_tools import build_archive
from runtime_state import read_json


class BetaInstallTests(unittest.TestCase):
    def package(self, root, version):
        source=root/("source-"+version);source.mkdir()
        (source/"plugin.json").write_text(json.dumps({"name":"codex-pulse","version":version}))
        (source/"overlay.py").write_text("version="+repr(version))
        (source/"test_example.py").write_text("test fixture")
        (source/"rollback.ps1").write_text("legacy plugin rollback must not enter portable beta")
        (source/"回退上一版本.cmd").write_text("legacy entry")
        archive=root/(version+".zip")
        build_archive(source,archive,include_tests=False)
        return archive

    def test_fresh_install_upgrade_actual_rollback_preserve_preferences(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);target=root/"beta with spaces"
            v1=self.package(root,"0.6.17");v2=self.package(root,"0.6.18-beta.1")
            manage.install(v1,target)
            settings=target/"data"/"settings.json";settings.parent.mkdir()
            original=b'{"theme_color":"#166daa","font_size":17,"unknown":{"preserve":true}}'
            settings.write_bytes(original)
            manage.install(v2,target)
            self.assertEqual(read_json(target/"installation.json")["current"],"0.6.18-beta.1")
            manage.rollback(target,dry_run=True)
            manage.rollback(target)
            self.assertEqual(read_json(target/"installation.json")["current"],"0.6.17")
            self.assertEqual(settings.read_bytes(),original)
            self.assertFalse((target/"versions"/"0.6.18-beta.1"/"test_example.py").exists())
            self.assertFalse((target/"versions"/"0.6.18-beta.1"/"rollback.ps1").exists())
            self.assertFalse((target/"versions"/"0.6.18-beta.1"/"回退上一版本.cmd").exists())
            self.assertTrue((target/"controller"/"manage.py").exists())

    def test_rollback_preserves_later_user_edits_and_active_version(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);target=root/"beta"
            manage.install(self.package(root,"0.6.17"),target)
            manage.install(self.package(root,"0.6.18-beta.1"),target)
            edited=target/"versions"/"0.6.17"/"overlay.py";edited.write_text("user edit")
            before=(target/"installation.json").read_bytes()
            with self.assertRaisesRegex(ValueError,"changed"):
                manage.rollback(target)
            self.assertEqual((target/"installation.json").read_bytes(),before)
            self.assertEqual(edited.read_text(),"user edit")

    def test_unrelated_target_and_archive_path_escape_are_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);target=root/"notes";target.mkdir();(target/"note.txt").write_text("keep")
            with self.assertRaisesRegex(ValueError,"empty folder"):
                manage.install(self.package(root,"0.6.17"),target)
            with self.assertRaisesRegex(ValueError,"Invalid package version"):
                manage.version_dir(root,"../outside")
            self.assertEqual(list(target.iterdir()),[target/"note.txt"])
