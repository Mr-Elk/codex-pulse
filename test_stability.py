import unittest
from unittest.mock import patch,Mock,call
from types import SimpleNamespace

from overlay_geometry import Rect, stable_position, resize_from_left,place
from overlay_stability import Motion
import test_layering as layering


class StabilityTests(unittest.TestCase):
    def stationary_window(self):
        window = layering.YieldTests().window()
        window.interaction_open = False
        return window

    def test_100_stationary_ticks_place_only_once(self):
        window = self.stationary_window()
        with patch("overlay.time.monotonic", return_value=window.context_at):
            for _ in range(100):
                window.tick()
        self.assertEqual(window.win.show_without_focus.call_count, 1)
        self.assertEqual(window.root.geometry.call_count, 1)
        self.assertEqual(window.position_updates, 1)

    def test_pixel_noise_is_held_but_a_real_move_or_size_change_is_applied(self):
        original = Rect(100, 100, 500, 138)
        self.assertEqual(stable_position(original, Rect(102, 99, 502, 137)), original)
        for candidate in (Rect(103, 100, 503, 138), Rect(100, 100, 501, 138), Rect(100, 100, 500, 139)):
            self.assertEqual(stable_position(original, candidate), candidate)

    def test_host_movement_is_immediate_even_inside_the_pixel_deadband(self):
        window = self.stationary_window()
        window.tick()
        before = window.last_bounds
        window.win.client_rect.return_value = Rect(1, 1, 1001, 801)
        window.tick()
        self.assertEqual(window.last_bounds.left, before.left+1)
        self.assertEqual(window.last_bounds.top, before.top+1)
        self.assertEqual(window.position_updates, 2)

    def test_refresh_unknown_and_generation_never_toggle_the_shell(self):
        window = self.stationary_window()
        fixture = layering.YieldTests()
        for popup in (None,False,True,None)*25:
            fixture.context(window,popup)
            window.snapshot["request_pending"] = True
            window.tick()
            self.assertTrue(window.visible)
        window.win.hide.assert_not_called()
        self.assertEqual(window.position_updates,1)

    def test_obstruction_moves_the_shell_above_it_without_hiding(self):
        window = self.stationary_window()
        window.tick()
        before = window.last_bounds
        window.avoid_rect = Rect(before.left,before.top-40,before.right,before.bottom+20)
        window.tick()
        self.assertTrue(window.visible)
        self.assertLess(window.last_bounds.bottom,window.avoid_rect.top)
        window.win.hide.assert_not_called()

    def test_motion_retarget_does_not_restart_on_every_refresh(self):
        motion = Motion(0.2)
        first,second = Rect(0,100,200,144),Rect(0,20,200,64)
        motion.retarget(first,255,0,immediate=True)
        motion.retarget(second,255,1)
        halfway = motion.sample(1.1)[0]
        self.assertTrue(second.top < halfway.top < first.top)
        motion.retarget(second,255,1.1)
        self.assertEqual(motion.sample(1.21),(second,255,True))

    def test_desktop_capsule_stays_visible_while_other_apps_are_active(self):
        window = self.stationary_window()
        window.display_mode = "desktop"
        window.win.work_area.return_value = Rect(0,0,1920,1040)
        window.win.active_target.return_value = False
        window.tick()
        self.assertTrue(window.visible)
        self.assertIsNone(window.binding.identity)
        self.assertLess(window.last_bounds.width,250)

    def test_return_to_composer_demotes_both_own_surfaces_before_attaching_app(self):
        window=self.stationary_window()
        window.surface=SimpleNamespace(material=SimpleNamespace(hwnd=201))
        window.display_mode="desktop"
        window.save_preferences=Mock()
        window.set_display_mode("composer")
        operations=[c for c in window.win.mock_calls if c[0] in ("set_floating","own_overlay")]
        self.assertEqual(operations,[call.set_floating(window.hwnd,False),call.set_floating(201,False),
                                     call.own_overlay(window.hwnd,window.target["hwnd"]),call.own_overlay(201,window.target["hwnd"])])

    def test_capsule_grip_click_and_center_click_expand_desktop_statistics(self):
        window=self.stationary_window();window.display_mode="desktop";window.drag=(10,10)
        window.win.work_area.return_value=Rect(0,0,1920,1040)
        window.drag_moved=False;window.drag_control="drag";window.save_preferences=Mock()
        window.drag_end(None)
        self.assertFalse(window.compact)
        window.compact=True
        window.drag=(70,10);window.drag_control=None;window.drag_end(None)
        self.assertFalse(window.compact)

    def test_width_animation_keeps_left_pivot_and_has_intermediate_sizes(self):
        motion=Motion(.2)
        full=Rect(240,300,1048,356);capsule=resize_from_left(full,220,56)
        motion.retarget(full,255,0,immediate=True);motion.retarget(capsule,255,1)
        shrinking=[motion.sample(t)[0] for t in (1,1.04,1.08,1.12,1.2)]
        self.assertTrue(all(r.left==240 and (r.top+r.bottom)/2==328 for r in shrinking))
        self.assertGreater(len({r.width for r in shrinking}),3)
        self.assertEqual(shrinking[0].width,808);self.assertEqual(shrinking[-1].width,220)
        motion.retarget(full,255,2)
        growing=[motion.sample(t)[0] for t in (2,2.04,2.08,2.12,2.2)]
        self.assertTrue(all(r.left==240 for r in growing))
        self.assertEqual([r.width for r in growing],sorted(r.width for r in growing))

    def test_compact_toggle_saves_the_same_left_pivot_and_survives_reload(self):
        import overlay_style as style
        window=self.stationary_window();window.display_mode="desktop";window.compact=False
        full=Rect(240,300,240+style.width_for(),356)
        window.font_size=15;window.last_bounds=full
        area=Rect(0,0,1920,1040);window.win.work_area.return_value=area;window.save_preferences=Mock()
        window.toggle_compact()
        compact=place(area,220,56,manual=window.desktop_position)
        self.assertEqual(compact,Rect(240,300,460,356))
        window.last_bounds=compact;window.toggle_compact()
        self.assertEqual(place(area,style.width_for(),56,manual=window.desktop_position),full)


if __name__ == "__main__":
    unittest.main()
