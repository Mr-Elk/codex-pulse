"""Escape cancellation must never turn a focus change into process exit."""
from types import SimpleNamespace
from unittest.mock import Mock
import threading,unittest
from overlay import Overlay
import test_panel_layout as fixture


class EscapeRoutingTests(unittest.TestCase):
    def start_preview(self,p):
        sorter=p.metric_sorter;key=sorter.order[1];row=sorter.rows[key]
        handle=next(w for w in row.winfo_children() if w.cget('cursor')=='fleur')
        start=SimpleNamespace(x_root=row.winfo_rootx()+12,y_root=row.winfo_rooty()+20)
        p.owner.select_metrics=Mock()
        sorter.start(key,handle,start)
        sorter.move(SimpleNamespace(x_root=start.x_root,y_root=start.y_root+80))
        self.assertNotEqual(sorter.preview,sorter.order)
        return sorter,handle

    def test_repeated_escape_on_strip_never_requests_process_exit(self):
        owner=Overlay.__new__(Overlay)
        owner.settings_panel=None;owner.metric_tooltip=Mock();owner.close=Mock();owner.stop=threading.Event()
        for _ in range(20):self.assertEqual(owner.escape(),'break')
        owner.close.assert_not_called();self.assertFalse(owner.stop.is_set())
        self.assertEqual(owner.metric_tooltip.hide.call_count,20)

    def test_strip_escape_restores_active_preview_without_closing_settings(self):
        with fixture.PanelLayoutTests().panel() as (p,root,_):
            original=list(p.owner.metric_order);sorter,handle=self.start_preview(p)
            self.assertEqual(p.owner.escape(),'break');root.update()
            self.assertFalse(p.closed);self.assertIs(p.owner.settings_panel,p)
            self.assertIsNone(sorter.active);self.assertIsNone(handle.grab_current())
            self.assertIsNone(sorter.animation);self.assertIsNone(sorter.scroll_job)
            self.assertEqual(sorter.preview,original);self.assertEqual(p.owner.metric_order,original)
            p.owner.select_metrics.assert_not_called();p.owner.close.assert_not_called()

    def test_settings_escape_cancels_drag_before_dismissing_the_panel(self):
        for scale in (1,1.5,2):
            with self.subTest(scale=scale),fixture.PanelLayoutTests().panel(scale) as (p,root,_):
                original=list(p.owner.metric_order);sorter,_=self.start_preview(p)
                self.assertEqual(p.escape(),'break');root.update()
                self.assertFalse(p.closed);self.assertEqual(sorter.preview,original)
                self.assertEqual(p.owner.metric_order,original);p.owner.select_metrics.assert_not_called()
                self.assertEqual(p.escape(),'break');root.update()
                self.assertTrue(p.closed);self.assertIsNone(p.owner.settings_panel)
                p.owner.close.assert_not_called();self.assertFalse(p.owner.stop.is_set())

    def test_escape_remains_safe_after_drag_loses_focus_or_panel_is_gone(self):
        with fixture.PanelLayoutTests().panel() as (p,root,_):
            original=list(p.owner.metric_order);sorter,_=self.start_preview(p)
            sorter.cancel()  # The existing FocusOut route can run before Escape.
            for _ in range(5):p.owner.escape()
            self.assertFalse(p.closed);self.assertEqual(p.owner.metric_order,original)
            p.close();root.update()
            for _ in range(5):p.owner.escape()
            p.owner.close.assert_not_called();p.owner.select_metrics.assert_not_called()
            self.assertFalse(p.owner.stop.is_set())


if __name__=='__main__':unittest.main()
