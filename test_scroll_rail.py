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
    panel = layout.PanelLayoutTests.panel

    def test_external_rails_do_not_reflow_content_and_fade_after_activity(self):
        for scale in (1, 1.25, 1.5, 2):
            with self.subTest(scale=scale), self.panel(scale) as (panel, root, area):
                bar = panel.session_scroll
                right = panel.choices.winfo_rootx()+panel.choices.winfo_width()
                self.assertGreaterEqual(bar.winfo_rootx(), right)
                self.assertGreaterEqual(panel.scroller.winfo_rootx(), bar.winfo_rootx()+bar.winfo_width())
                self.assertLessEqual(panel.scroller.winfo_rootx()+panel.scroller.winfo_width(),
                                     panel.window.winfo_rootx()+panel.window.winfo_width()-panel.px(6))
                widths = (panel.content.winfo_width(), panel.choices.winfo_width(), panel.tree.winfo_width())
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
                self.assertEqual(widths, (panel.content.winfo_width(), panel.choices.winfo_width(), panel.tree.winfo_width()))
                panel.search.set("不存在的关键词"); root.update()
                self.assertFalse(bar.overflow)
                self.assertEqual(widths, (panel.content.winfo_width(), panel.choices.winfo_width(), panel.tree.winfo_width()))

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

    def test_short_screen_rails_stay_outside_content_and_cancel_timers_on_tab_close(self):
        with self.panel(scale=1.5, work_height=520) as (panel, root, area):
            outer, inner = panel.scroller, panel.session_scroll
            self.assertTrue(outer.overflow)
            for position in (0, .4, 1):
                panel.content.yview_moveto(position); root.update()
                if inner.winfo_manager():
                    self.assertGreaterEqual(inner.winfo_rooty(), panel.content.winfo_rooty())
                    self.assertLessEqual(inner.winfo_rooty()+inner.winfo_height(),
                                         panel.content.winfo_rooty()+panel.content.winfo_height())
                    self.assertLessEqual(inner.winfo_rootx()+inner.winfo_width(), outer.winfo_rootx())
                self.assertGreaterEqual(outer.winfo_rootx(), panel.content.winfo_rootx()+panel.content.winfo_width())
            inner.leave(); outer.leave()
            panel.show_tab("display"); root.update()
            self.assertTrue(inner.disposed)
            self.assertIsNone(inner.hide_job)
            self.assertIsNone(inner.fade_job)
            width = panel.content.winfo_width()
            panel.content.yview_moveto(1); root.update()
            outer.enter(); theme.activate("#36824b"); outer.redraw(); root.update()
            self.assertEqual(panel.content.winfo_width(), width)
            panel.close(); root.update()
            self.assertTrue(outer.disposed)
            self.assertIsNone(outer.hide_job)
            self.assertIsNone(outer.fade_job)
            settle(root, 1.3)
