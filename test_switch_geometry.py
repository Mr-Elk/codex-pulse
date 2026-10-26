import unittest,tkinter as tk
from unittest.mock import Mock
from test_panel_layout import PanelLayoutTests

class SwitchGeometryTests(unittest.TestCase):
    def test_track_is_not_clipped_by_canvas_borders_at_supported_scales(self):
        from settings_panel import Toggle
        for scale in (1,1.25,1.5,2):
            with self.subTest(scale=scale),PanelLayoutTests().panel(scale) as (p,root,_):
                var=tk.BooleanVar(master=root,value=True);button=Toggle(p.body,var,Mock(),scale);button.pack();root.update()
                self.assertEqual(int(button.cget('highlightthickness')),0)
                self.assertEqual((button.art.width(),button.art.height()),(button.winfo_width(),button.winfo_height()))
                x=round(23*scale)
                self.assertEqual(button.art.get(x,round(3*scale)),(255,255,255))
                self.assertNotEqual(button.art.get(x,round(6*scale)),(255,255,255))
                self.assertNotEqual(button.art.get(x,round(28*scale)),(255,255,255))
                self.assertEqual(button.art.get(x,round(31*scale)),(255,255,255))
    def test_pointer_press_does_not_commit_and_release_outside_cancels(self):
        from settings_panel import Toggle
        with PanelLayoutTests().panel() as (p,root,_):
            var=tk.BooleanVar(master=root,value=False);action=Mock();button=Toggle(p.body,var,action,1);button.pack();root.update()
            button.event_generate('<ButtonPress-1>',x=12,y=14);root.update();self.assertFalse(var.get())
            button.event_generate('<ButtonRelease-1>',x=-10,y=14);root.update();self.assertFalse(var.get());action.assert_not_called()
            button.event_generate('<ButtonPress-1>',x=12,y=14);button.event_generate('<ButtonRelease-1>',x=12,y=14);root.update();self.assertTrue(var.get());action.assert_called_once()
    def test_keyboard_release_commits_once_and_disabled_state_is_inert(self):
        from settings_panel import Toggle
        with PanelLayoutTests().panel() as (p,root,_):
            var=tk.BooleanVar(master=root,value=False);action=Mock();button=Toggle(p.body,var,action,1);button.pack();root.update()
            button.key_press(None);button.key_press(None);self.assertFalse(var.get());button.key_release(None);self.assertTrue(var.get());action.assert_called_once()
            button.configure(state='disabled');root.update();button.toggle();button.key_press(None);button.key_release(None);self.assertTrue(var.get());action.assert_called_once();self.assertEqual(str(button.cget('takefocus')),'0')
            button.configure(state='normal');self.assertEqual(str(button.cget('takefocus')),'1')

class ImmediatePresentationTests(unittest.TestCase):
    def test_logo_release_commits_final_content_size_before_next_tick(self):
        from test_quick_interactions import QuickInteractionTests
        fixture=QuickInteractionTests()
        for mode in ('desktop','composer'):
            with self.subTest(mode=mode):
                owner=fixture.owner(mode,True)
                owner.tick()
                before=owner.last_bounds
                owner.drag_end(fixture.press(owner))
                factor=owner.scale*owner.font_size/15
                self.assertFalse(owner.compact)
                self.assertEqual(owner.last_bounds.width,round(owner.desired_width()*factor))
                self.assertEqual(owner.opacity,255)
                self.assertTrue(owner.visible)
                owner.drag_end(fixture.press(owner))
                self.assertTrue(owner.compact)
                self.assertEqual(owner.last_bounds.width,round(owner.desired_width()*factor))
                self.assertEqual(owner.opacity,255)
                owner.win.hide.assert_not_called()
