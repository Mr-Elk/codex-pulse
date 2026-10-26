import unittest
from unittest.mock import patch,Mock,call
from types import SimpleNamespace

from overlay_geometry import Rect, stable_position, resize_from_left,place
from overlay_stability import Motion
import test_layering as layering


class StabilityTests(unittest.TestCase):
    def test_presentation_frames_use_final_content_size_from_the_first_frame(self):
        from product_strip import layout_width
        from strip_renderer import render
        from test_strip_renderer import SNAPSHOT
        data={**SNAPSHOT,'visible_metrics':('cache','context','rounds','quota','recent','reset','credits'),
              'quota_display':{'quota':'25%','recent':'4%','reset':'6d4h','credits':'2'},
              'quota_config':{'capsule_primary':'quota','capsule_secondary':'recent'}}
        for font in (13,15,17):
            for dpi in (1,1.5,2):
                factor=font/15*dpi
                expanded={**data,'font_size':font};capsule={**expanded,'capsule':True}
                height=round({13:36,15:40,17:44}[font]*dpi)
                a=Rect(100,100,100+round(layout_width(capsule)*factor),100+height)
                b=Rect(100,100,100+round(layout_width(expanded)*factor),100+height)
                motion=Motion(.18);motion.retarget(a,255,0,immediate=True)
                for start,target,snapshot,keys in ((a,b,expanded,list(data['visible_metrics'])),(b,a,capsule,['quota','recent'])):
                    motion.retarget(start,255,1,immediate=True);motion.retarget(target,255,2)
                    for at in (2,2.001,2.016,2.08,2.18):
                        frame,alpha,_=motion.sample(at)
                        self.assertEqual((frame.width,frame.height),(target.width,target.height))
                        self.assertEqual(alpha,255)
                        _,cells=render(snapshot,frame.width,factor)
                        self.assertEqual([c['key'] for c in cells],keys)
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

    def test_first_show_fade_progresses_instead_of_resetting_while_invisible(self):
        window=self.stationary_window();window.visible=False;window.applied_bounds=None;window.last_bounds=None
        window.motion=Motion(.18);rect=Rect(100,300,500,340)
        for now in (1.,1.016,1.032,1.2):
            with patch('overlay.time.monotonic',return_value=now):window.position_overlay(rect)
        self.assertTrue(window.visible);self.assertEqual(window.opacity,255)
        self.assertEqual(window.last_bounds,rect)

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

    def test_desktop_strip_stays_expanded_while_other_apps_are_active(self):
        window = self.stationary_window()
        window.display_mode = "desktop"
        window.win.work_area.return_value = Rect(0,0,1920,1040)
        window.win.active_target.return_value = False
        window.tick()
        self.assertTrue(window.visible)
        self.assertIsNone(window.binding.identity)
        self.assertFalse(window.is_capsule())
        self.assertEqual(window.capsule_status(),"未在会话")

    def test_return_to_composer_demotes_both_own_surfaces_before_attaching_app(self):
        window=self.stationary_window()
        window.surface=SimpleNamespace(material=SimpleNamespace(hwnd=201))
        window.display_mode="desktop"
        window.save_preferences=Mock()
        window.commit_presentation=Mock()
        window.set_display_mode("composer")
        operations=[c for c in window.win.mock_calls if c[0] in ("set_floating","own_overlay")]
        self.assertEqual(operations,[call.set_floating(window.hwnd,False),call.set_floating(201,False),
                                     call.own_overlay(window.hwnd,window.target["hwnd"]),call.own_overlay(201,window.target["hwnd"])])

    def test_only_logo_expands_capsule_and_metrics_cannot_expand_it(self):
        window=self.stationary_window();window.display_mode="desktop";window.compact=True;window.drag=(10,10)
        window.win.work_area.return_value=Rect(0,0,1920,1040)
        window.drag_moved=False;window.drag_control="drag";window.save_preferences=Mock()
        window.drag_end(None)
        self.assertFalse(window.compact)
        window.compact=True
        window.drag=None;window.drag_control=None;window.drag_end(None)
        self.assertTrue(window.compact)

    def test_presentation_size_changes_keep_the_left_pivot_without_intermediate_clipping(self):
        motion=Motion(.2)
        full=Rect(240,300,1048,356);capsule=resize_from_left(full,220,56)
        motion.retarget(full,255,0,immediate=True);motion.retarget(capsule,255,1)
        shrinking=[motion.sample(t)[0] for t in (1,1.04,1.08,1.12,1.2)]
        self.assertTrue(all(r.left==240 and (r.top+r.bottom)/2==328 for r in shrinking))
        self.assertEqual({r.width for r in shrinking},{220})
        motion.retarget(full,255,2)
        growing=[motion.sample(t)[0] for t in (2,2.04,2.08,2.12,2.2)]
        self.assertTrue(all(r.left==240 for r in growing))
        self.assertEqual({r.width for r in growing},{808})

    def test_compact_toggle_saves_the_same_left_pivot_and_survives_reload(self):
        import overlay_style as style
        window=self.stationary_window();window.display_mode="desktop";window.compact=False
        full_width=round(window.desired_width())
        full=Rect(240,300,240+full_width,340)
        window.font_size=15;window.last_bounds=full
        area=Rect(0,0,1920,1040);window.win.work_area.return_value=area;window.save_preferences=Mock()
        window.toggle_compact()
        capsule_width=window.desired_width()
        compact=place(area,capsule_width,40,manual=window.desktop_position)
        self.assertEqual(compact,Rect(240,300,240+capsule_width,340))
        window.last_bounds=compact;window.toggle_compact()
        self.assertEqual(place(area,round(window.desired_width()),40,manual=window.desktop_position),full)


if __name__ == "__main__":
    unittest.main()
