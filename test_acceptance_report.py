from pathlib import Path
import json,tempfile,unittest
from unittest.mock import patch
import acceptance_report as report


class AcceptanceReportTests(unittest.TestCase):
    def target(self,root):
        (root/'data').mkdir();(root/'installation.json').write_text(json.dumps({'name':'codex-pulse-beta','current':'0.7.0-beta.10','previous':'0.7.0-beta.6','python':'private-python-path'}))
        (root/'data/settings.json').write_text(json.dumps({'binding':'private-account-id','title':'private-chat-title'}))
        return root

    def test_export_has_allowlisted_fields_and_no_private_runtime_or_settings(self):
        with tempfile.TemporaryDirectory() as d:
            root=self.target(Path(d));state={'running':True,'display_mode':'desktop','bound_title':'private-chat-title','account_id':'private-account-id','path':'private-python-path','render_error':'private-error-path'}
            with patch.object(report.manage,'verify_version'):
                result=report.collect(root,probe=lambda _:state,env={'os':'Windows'})
            text=json.dumps(result)
            for secret in ('private-chat-title','private-account-id','private-python-path','private-error-path'):self.assertNotIn(secret,text)
            self.assertIs(result['runtime']['render_error'],True);self.assertTrue(result['runtime']['running'])

    def test_setting_comparison_reports_changes_without_rewriting_them(self):
        with tempfile.TemporaryDirectory() as d:
            root=self.target(Path(d))
            with patch.object(report.manage,'verify_version'):
                before=report.collect(root,probe=lambda _:{},env={})
                self.assertTrue(report.collect(root,before,probe=lambda _:{},env={})['settings_same_as_baseline'])
                changed=b'{"new_user_preference":true}';(root/'data/settings.json').write_bytes(changed)
                self.assertFalse(report.collect(root,before,probe=lambda _:{},env={})['settings_same_as_baseline'])
            self.assertEqual((root/'data/settings.json').read_bytes(),changed)

    def test_unrelated_folder_never_probes_a_runtime_and_integrity_failure_is_explicit(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);probe=unittest.mock.Mock()
            self.assertFalse(report.collect(root,probe=probe,env={})['installation']['managed']);probe.assert_not_called()
            self.target(root)
            with patch.object(report.manage,'verify_version',side_effect=ValueError('private changed file path')):
                result=report.collect(root,probe=lambda _:{},env={})
            self.assertFalse(result['file_integrity']);self.assertNotIn('private changed',json.dumps(result))


if __name__=='__main__':unittest.main()
