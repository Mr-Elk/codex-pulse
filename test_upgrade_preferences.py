import json,tempfile,unittest
from pathlib import Path
import overlay_settings as preferences
from quota_service import METRIC_KEYS


class UpgradePreferencesTests(unittest.TestCase):
    def test_public_old_version_keeps_effective_metric_order(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'settings.json'
            raw={'visible_metrics':['speed','tokens','cache'],'display':{'mode':'desktop','position':{'center_ratio':.68,'bottom_gap':90},'compact':False}}
            path.write_text(json.dumps(raw),encoding='utf-8');before=path.read_bytes()
            display=preferences.load_display(path)
            self.assertEqual(display['metric_order'][:3],['speed','tokens','cache'])
            self.assertEqual(set(display['metric_order']),set(METRIC_KEYS))
            self.assertEqual(display['position'],raw['display']['position'])
            self.assertEqual(path.read_bytes(),before)

    def test_v19_saved_order_has_priority_and_fresh_profile_uses_defaults(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'settings.json'
            self.assertEqual(preferences.load_display(path)['metric_order'],list(METRIC_KEYS))
            raw={'visible_metrics':['speed','tokens'],'display':{'presentation_schema':19,'metric_order':['quota','cache']}}
            path.write_text(json.dumps(raw),encoding='utf-8')
            self.assertEqual(preferences.load_display(path)['metric_order'][:2],['quota','cache'])


if __name__=='__main__':unittest.main()
