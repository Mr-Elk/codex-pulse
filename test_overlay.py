import unittest
import json
from pathlib import Path
import tempfile

from overlay_geometry import Rect, compact, place, remember, segments
import overlay_settings as preferences
import overlay_style as style


class StyleTests(unittest.TestCase):
    def test_normal_width_retains_all_columns_and_even_outer_padding(self):
        columns = style.columns(style.WIDTH)
        self.assertEqual([c.key for c in columns], list(style.ORDER))
        self.assertEqual(columns[0].x, style.INSET)
        self.assertAlmostEqual(columns[-1].x+columns[-1].width, style.WIDTH-style.INSET)
        for first,second in zip(columns, columns[1:]):
            self.assertEqual(first.x+first.width, second.x)

    def test_narrow_width_hides_secondary_metrics_before_cropping(self):
        columns = style.columns(384)
        self.assertEqual([c.key for c in columns], ["speed", "tokens", "cache"])
        self.assertLessEqual(columns[-1].x+columns[-1].width, 384-style.INSET+1e-6)
        self.assertEqual(style.columns(100), [])

    def test_waiting_state_keeps_same_columns_and_reports_unknown_values(self):
        data = style.metrics({"available": False})
        self.assertEqual(set(data), set(style.ORDER))
        self.assertEqual(data["speed"].runs[0].text, "—")
        self.assertEqual(data["context"].runs[0].text, "—")
        self.assertIsNone(data["context"].progress)

    def test_counts_use_one_scope_and_pending_speed_is_not_previous_speed(self):
        snapshot={"available":True,"rounds":4,"requests":96,"turn_requests":9,
                  "request_pending":True,"latest_tps_estimate":42,"usage":{"total_tokens":1000000}}
        data=style.metrics(snapshot)
        self.assertEqual(data["rounds"].runs[2].text,"96")
        self.assertEqual([run.text for run in data["speed"].runs],["生成中"])
        self.assertEqual("".join(run.text for run in data["tokens"].runs),"1.00M")
        self.assertEqual(data["tokens"].runs[-1].role,"label")


def expected_preferences(font_size=15, position=None):
    return {"font_size": font_size, "position": position, "locked": True, "visible_metrics": list(style.ORDER)}


class PreferenceTests(unittest.TestCase):
    def test_composer_relative_offset_is_preserved_across_reload(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/"settings.json"
            position={"anchor":"composer","center_ratio":0.46,"gap":8}
            preferences.save(path,13,position)
            self.assertEqual(preferences.load(path),expected_preferences(13,position))
    def test_upgrade_retains_manual_position_with_larger_default_font(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "settings.json"
            legacy = Path(folder) / "pulse-position.json"
            original = {"center_ratio": 0.3177083333333333, "bottom_gap": 221.0}
            legacy.write_text(json.dumps(original), encoding="utf-8")
            value = preferences.load(path, legacy)
            self.assertEqual(value, expected_preferences(15,original))
            preferences.save(path, **{"font_size": value["font_size"], "position": value["position"]})
            self.assertEqual(preferences.load(path), value)
            self.assertEqual(json.loads(legacy.read_text(encoding="utf-8")), original)

    def test_saved_font_and_auto_placement_override_legacy_position(self):
        with tempfile.TemporaryDirectory() as folder:
            path, legacy = Path(folder) / "settings.json", Path(folder) / "old.json"
            legacy.write_text('{"center_ratio":0.5,"bottom_gap":200}', encoding="utf-8")
            preferences.save(path, 17, None)
            self.assertEqual(preferences.load(path, legacy), expected_preferences(17))

    def test_invalid_preferences_do_not_create_bad_coordinates_or_font(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "settings.json"
            path.write_text('{"font_size":10000,"position":{"center_ratio":NaN,"bottom_gap":-1}}', encoding="utf-8")
            self.assertEqual(preferences.load(path), expected_preferences())
            path.write_text('[]', encoding="utf-8")
            self.assertEqual(preferences.load(path), expected_preferences())


class PlacementTests(unittest.TestCase):
    def test_drag_offset_follows_composer_when_pane_moves_or_resizes(self):
        host=Rect(0,0,1920,1032)
        composer=Rect(735,914,1472,1012)
        settings=remember(host,Rect(743,868,1431,906),composer=composer)
        moved=Rect(350,650,950,780)
        result=place(host,688,56,moved,settings)
        self.assertEqual(result.width,688)
        self.assertEqual(result.bottom,642)
        self.assertLessEqual(abs(result.left-(moved.left+moved.width*settings["left_ratio"])),1)

    def test_draft_height_change_moves_strip_above_new_composer_top(self):
        host=Rect(0,0,1920,1032)
        composer=Rect(735,914,1472,1012)
        settings=remember(host,Rect(743,868,1431,906),composer=composer)
        before=place(host,688,56,composer,settings)
        after=place(host,688,56,Rect(735,764,1472,1012),settings)
        self.assertEqual(after.top,before.top-150)
        self.assertEqual(after.bottom,756)

    def test_composer_gap_scales_with_monitor_dpi(self):
        result=place(Rect(0,0,3840,2064),1376,112,Rect(1470,1828,2944,2024),
                     {"anchor":"composer","center_ratio":0.5,"gap":8},scale=2)
        self.assertEqual(result.bottom,1812)

    def test_left_aligns_above_composer_in_split_pane(self):
        host=Rect(0,0,1920,1032)
        composer=Rect(275,890,990,1010)
        result=place(host,560,25,composer)
        self.assertEqual(result,Rect(299,858,859,883))
        self.assertLess(result.bottom,composer.top)

    def test_follows_host_move_without_overlapping_input(self):
        result=place(Rect(100,100,2020,1132),560,25,Rect(375,990,1090,1110))
        self.assertEqual(result,Rect(399,958,959,983))

    def test_manual_position_survives_move_resize_and_dpi_change(self):
        old=Rect(0,0,1920,1032)
        strip=Rect(352,858,912,883)
        settings=remember(old,strip)
        moved=place(Rect(100,100,2020,1132),560,25,manual=settings)
        self.assertEqual(moved,Rect(452,958,1012,983))
        highdpi=place(Rect(0,0,2880,1548),840,38,manual=settings,scale=1.5)
        self.assertLess(abs(highdpi.left-528),2)
        self.assertLess(abs(highdpi.top-1287),2)

    def test_small_host_keeps_overlay_inside_window(self):
        host=Rect(-1200,100,-800,700)
        result=place(host,560,25,manual={"center_ratio":2,"bottom_gap":-100})
        self.assertGreaterEqual(result.left,host.left)
        self.assertLessEqual(result.right,host.right)
        self.assertLessEqual(result.bottom,host.bottom)

    def test_missing_metrics_remain_unknown(self):
        self.assertIn("TPS —",segments({"available":False}))
        s={"available":True,"rounds":1,"requests":2,"turn_requests":2,"latest_tps_estimate":None,
           "cache_hit_percent":None,"context_percent_estimate":None,"usage":{"total_tokens":12000}}
        self.assertIn("TPS —",segments(s))
        self.assertIn("缓存 —",segments(s))
        self.assertIn("12.0k tok",segments(s))


if __name__=="__main__":
    unittest.main()
