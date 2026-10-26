"""Release recovery must not point back to the known Escape-exit build."""
from pathlib import Path
import hashlib,json,tempfile,unittest
from unittest.mock import patch
import manage
import test_beta_install as fixture
from runtime_state import read_json,atomic_json


class RecoveryInstallTests(unittest.TestCase):
    def packages(self,root):
        maker=fixture.BetaInstallTests()
        return {v:maker.package(root,v) for v in ('0.7.0-beta.5','0.7.0-beta.6','0.7.0-beta.10')}

    def test_fresh_candidate_has_an_explicit_verified_recovery(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);p=self.packages(root);target=root/'fresh'
            with patch.object(manage,'RECOVERY_SHA256',hashlib.sha256(p['0.7.0-beta.6'].read_bytes()).hexdigest()):
                manage.install(p['0.7.0-beta.10'],target,recovery_archive=p['0.7.0-beta.6'])
            self.assertEqual(read_json(target/'installation.json')['previous'],'0.7.0-beta.6')
            manage.verify_version(target,'0.7.0-beta.6');manage.rollback(target)
            self.assertEqual(read_json(target/'installation.json')['current'],'0.7.0-beta.6')

    def test_upgrade_from_bad_build_rolls_back_to_six_and_preserves_preferences(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);p=self.packages(root);target=root/'用户 空格'
            manage.install(p['0.7.0-beta.5'],target)
            settings=target/'data/settings.json';settings.parent.mkdir();settings.write_bytes(b'{"theme_color":"#166daa","unknown":[1,2]}')
            before=settings.read_bytes()
            with patch.object(manage,'RECOVERY_SHA256',hashlib.sha256(p['0.7.0-beta.6'].read_bytes()).hexdigest()):
                manage.install(p['0.7.0-beta.10'],target,recovery_archive=p['0.7.0-beta.6'])
                marker=(target/'installation.json').read_bytes();manage.rollback(target,dry_run=True)
                self.assertEqual((target/'installation.json').read_bytes(),marker)
                manage.rollback(target);self.assertEqual(read_json(target/'installation.json')['current'],'0.7.0-beta.6')
                manage.install(p['0.7.0-beta.10'],target,recovery_archive=p['0.7.0-beta.6'])
            self.assertEqual(settings.read_bytes(),before)
            self.assertEqual(read_json(target/'installation.json')['previous'],'0.7.0-beta.6')
            manage.verify_version(target,'0.7.0-beta.5')

    def test_unapproved_recovery_is_rejected_before_stopping_current_process(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);p=self.packages(root);target=root/'beta';manage.install(p['0.7.0-beta.6'],target)
            marker=(target/'installation.json').read_bytes()
            with patch.object(manage,'stop') as stop:
                for recovery in (p['0.7.0-beta.5'],p['0.7.0-beta.6']):
                    with self.assertRaisesRegex(ValueError,'verified beta.6'):
                        manage.install(p['0.7.0-beta.10'],target,recovery_archive=recovery)
                stop.assert_not_called()
            self.assertEqual((target/'installation.json').read_bytes(),marker)

    def test_changed_recovery_files_are_not_overwritten_and_process_is_not_stopped(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);p=self.packages(root);target=root/'beta';manage.install(p['0.7.0-beta.6'],target)
            changed=target/'versions/0.7.0-beta.6/overlay.py';changed.write_text('user changes')
            marker=(target/'installation.json').read_bytes()
            with patch.object(manage,'RECOVERY_SHA256',hashlib.sha256(p['0.7.0-beta.6'].read_bytes()).hexdigest()),patch.object(manage,'stop') as stop:
                with self.assertRaisesRegex(ValueError,'changed'):
                    manage.install(p['0.7.0-beta.10'],target,recovery_archive=p['0.7.0-beta.6'])
                stop.assert_not_called()
            self.assertEqual(changed.read_text(),'user changes');self.assertEqual((target/'installation.json').read_bytes(),marker)

    def test_known_bad_previous_is_rejected_without_stopping_or_pointer_changes(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);p=self.packages(root);target=root/'beta';manage.install(p['0.7.0-beta.6'],target)
            marker=read_json(target/'installation.json');marker['previous']='0.7.0-beta.5';atomic_json(target/'installation.json',marker)
            before=(target/'installation.json').read_bytes()
            with patch.object(manage,'stop') as stop:
                for dry in (True,False):
                    with self.assertRaisesRegex(ValueError,'known Escape'):
                        manage.rollback(target,dry_run=dry)
                stop.assert_not_called()
            self.assertEqual((target/'installation.json').read_bytes(),before)

    def test_install_without_recovery_does_not_offer_bad_previous(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);p=self.packages(root);target=root/'beta';manage.install(p['0.7.0-beta.5'],target)
            manage.install(p['0.7.0-beta.10'],target)
            self.assertIsNone(read_json(target/'installation.json')['previous'])
            with self.assertRaisesRegex(ValueError,'No previous'):manage.rollback(target)

    def test_conflicting_existing_candidate_is_rejected_before_stopping(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);p=self.packages(root);target=root/'beta';manage.install(p['0.7.0-beta.10'],target)
            source=root/'source-0.7.0-beta.10';(source/'overlay.py').write_text('different same-version package')
            from release_tools import build_archive
            build_archive(source,p['0.7.0-beta.10'],include_tests=False)
            with patch.object(manage,'stop') as stop:
                with self.assertRaisesRegex(ValueError,'different package contents'):manage.install(p['0.7.0-beta.10'],target)
                stop.assert_not_called()


if __name__=='__main__':unittest.main()
