"""Scroll affordance, content separation and reachable endpoints in our own UI."""
import time
from types import SimpleNamespace
import unittest

import test_panel_layout as layout
import theme


def settle(root, seconds):
    until = time.monotonic()+seconds
    while time.monotonic() < until:
        root.update()
        time.sleep(.005)
    root.update()


class ScrollRailTests(unittest.TestCase):
    from contextlib import contextmanager
    @contextmanager
    def panel(self,scale=1,work_height=900):
        from product_controls import session_dialog
        with layout.PanelLayoutTests().panel(scale,work_height) as (p,root,area):
            dialog=session_dialog(p);root.update()
            from types import SimpleNamespace
            proxy=SimpleNamespace(session_scroll=dialog.session_scroll,tree=dialog.session_tree,
                search=dialog.search,scale=scale,window=dialog)
            try:yield proxy,root,area
            finally:
                dialog.cancel_session()  # Closing an independent Tk root is idempotent.

    def test_external_rails_do_not_reflow_content_and_fade_after_activity(self):
        for scale in (1, 1.25, 1.5, 2):
            with self.subTest(scale=scale), self.panel(scale) as (panel, root, area):
                bar = panel.session_scroll
                widths = panel.tree.winfo_width()
                self.assertTrue(bar.overflow)
                bar.hovered = False
                bar.opacity = 0; bar.redraw()
                self.assertFalse(bar.find_all())
                panel.tree.yview_moveto(.5); root.update()
                self.assertEqual(bar.opacity, 1)
                self.assertEqual(bar.ink_width, 4*scale)
                bar.enter(); root.update()
                self.assertEqual(bar.ink_width, 6*scale)
                settle(root, 1.2)
                self.assertEqual(bar.opacity, 1, "hover must prevent hiding")
                bar.leave(); settle(root, 1.25)
                self.assertEqual(bar.opacity, 0)
                self.assertFalse(bar.find_all())
                self.assertEqual(widths,panel.tree.winfo_width())
                panel.search.set("不存在的关键词"); root.update()
                self.assertFalse(bar.overflow)
                self.assertEqual(widths,panel.tree.winfo_width())

    def test_drag_track_click_and_keyboard_reach_all_227_rows(self):
        with self.panel() as (panel, root, area):
            bar = panel.session_scroll
            bar.press(SimpleNamespace(y=bar.top+bar.thumb/2))
            bar.drag(SimpleNamespace(y=bar.winfo_height()+100)); root.update()
            self.assertAlmostEqual(panel.tree.yview()[1], 1)
            self.assertEqual(bar.ink_width, 6*panel.scale)
            self.assertTrue(bar.dragging)
            self.assertIsNone(bar.hide_job)
            bar.drag(SimpleNamespace(y=-100)); root.update()
            self.assertEqual(panel.tree.yview()[0], 0)
            bar.release(); root.update()
            bar.press(SimpleNamespace(y=bar.winfo_height())); bar.release(); root.update()
            self.assertAlmostEqual(panel.tree.yview()[1], 1)
            bar.event_generate("<MouseWheel>", delta=120); root.update()
            self.assertLess(panel.tree.yview()[1], 1)
            bar.move("moveto", 0); root.update()
            self.assertEqual(panel.tree.yview()[0], 0)
            bar.move("scroll", 1, "pages"); root.update()
            self.assertGreater(panel.tree.yview()[0], 0)
            self.assertEqual(len(panel.tree.get_children()), 227)

    def test_short_screen_modal_keeps_actions_reachable_and_disposes_timers(self):
        with self.panel(scale=1.5,work_height=520) as (p,root,area):
            self.assertLessEqual(p.window.winfo_height(),area.height)
            bar=p.session_scroll;bar.leave();p.window.cancel_session();root.update()
            self.assertTrue(bar.disposed);self.assertIsNone(bar.hide_job);self.assertIsNone(bar.fade_job)
            settle(root,.1)
