"""Viewport behavior: one session-list scrollbar without clipping controls."""
from contextlib import contextmanager
from pathlib import Path
import tempfile,time
from quota_service import METRIC_KEYS,clean_config
from test_quota import payload
from product_controls import session_dialog
import tkinter as tk
import unittest
from unittest.mock import Mock,patch

from overlay_geometry import Rect
from settings_panel import SettingsPanel
from strip_renderer import render
from test_strip_renderer import SNAPSHOT
import overlay_style as style
import test_layering as layering
import theme

SAMPLES=[]


class PanelLayoutTests(unittest.TestCase):
    @contextmanager
    def panel(self, scale=1, work_height=900, title="工作会话",tab="strip"):
        root=tk.Tk();root.withdraw();errors=[]
        root.report_callback_exception=lambda *args:errors.append(str(args[1]))
        owner=layering.YieldTests().window();owner.root=root;owner.scale=scale
        owner.display_mode="desktop";owner.render_strip=render;owner.snapshot=SNAPSHOT
        owner.quota_snapshot=payload(at=time.time());owner.quota_preferences=clean_config(None);owner.quota_service=None
        owner.visible_metrics=tuple(METRIC_KEYS);owner.metric_order=list(METRIC_KEYS)
        owner.metric_choices={key:tk.BooleanVar(root,value=True) for key in METRIC_KEYS}
        owner.lock_choice=tk.BooleanVar(root,value=True);owner.follow_choice=tk.BooleanVar(root,value=True)
        owner.thread_choice=tk.StringVar(root,value="a");owner.close=Mock()
        owner.theme_color=theme.DEFAULT;owner.expanded_mode="composer";owner.bound_title=title
        area=Rect(0,0,round(1280*scale),round(work_height*scale))
        owner.last_bounds=Rect(round(400*scale),round((work_height-60)*scale),round(1088*scale),round((work_height-20)*scale))
        owner.win.work_area.return_value=area
        catalog=[{"id":"a" if i==0 else str(i),"title":f"测试工作 {i:03d}"} for i in range(227)]
        with tempfile.TemporaryDirectory() as folder:
            owner.args.codex_home=Path(folder);owner.args.settings_file=Path(folder)/"settings.json"
            with patch("panel_chrome.Chrome"),patch.object(tk.Tk,"lift"),\
                 patch.object(tk.Tk,"focus_force"),patch("thread_catalog.recent",return_value=catalog):
                panel=None
                try:
                    panel=SettingsPanel(owner,area.right-20,area.bottom-20,tab=tab);owner.settings_panel=panel;panel.modal_open=True
                    root.update()
                    yield panel,root,area
                    self.assertEqual(errors,[])
                finally:
                    if panel:panel.close()
                    root.update()
                    root.destroy();theme.activate(theme.DEFAULT)

    def test_each_page_fits_normal_work_area_and_short_screen_scrolls(self):
        for scale in (1,1.25,1.5,2):
            with self.subTest(scale=scale),self.panel(scale) as (p,root,area):
                for tab in ('strip','quota','display'):
                    p.show_tab(tab);root.update()
                    self.assertLessEqual(p.window.winfo_y()+p.window.winfo_height(),area.bottom)
                    self.assertLessEqual(p.body.winfo_reqheight(),p.content.winfo_height()+2)
                for view in ('capsule','source'):
                    p.strip_view=view;p.show_tab('strip');root.update()
                    self.assertLessEqual(p.body.winfo_reqheight(),p.content.winfo_height()+2)
        with self.panel(1.5,520) as (p,root,area):
            self.assertTrue(p.scroller.overflow);self.assertLessEqual(p.window.winfo_height(),area.height)
            p.content.yview_moveto(1);root.update();self.assertAlmostEqual(p.content.yview()[1],1)

    def test_session_candidate_cancel_confirm_and_search(self):
        with self.panel() as (p,root,_):
            original=p.owner.binding
            dialog=session_dialog(p);root.update();self.assertEqual(len(dialog.session_tree.get_children()),227)
            dialog.session_tree.selection_set('15');root.update();self.assertEqual(p.owner.binding,original)
            dialog.cancel_session();root.update();self.assertEqual(p.owner.binding,original)
            dialog=session_dialog(p);root.update();dialog.search.set('不存在');root.update()
            self.assertEqual(dialog.session_tree.get_children(),());self.assertEqual(dialog.confirm_button.cget('state'),'disabled')
            dialog.search.set('026');root.update();self.assertEqual(len(dialog.session_tree.get_children()),1)
            dialog.session_tree.selection_set('26');root.update();dialog.confirm_session();root.update()
            self.assertEqual((p.owner.binding.mode,p.owner.binding.identity),('fixed','26'))

    def test_settings_uses_absolute_coordinates_on_left_and_upper_monitors(self):
        for area in (Rect(-1920,0,0,1080),Rect(-1920,-1080,0,0)):
            with self.subTest(area=area),self.panel() as (p,root,_):
                p.owner.win.work_area.return_value=area
                other=SettingsPanel(p.owner,area.right-20,area.bottom-20);other.modal_open=True;root.update()
                try:
                    self.assertGreaterEqual(other.window.winfo_x(),area.left);self.assertLessEqual(other.window.winfo_x()+other.window.winfo_width(),area.right)
                    self.assertGreaterEqual(other.window.winfo_y(),area.top);self.assertLessEqual(other.window.winfo_y()+other.window.winfo_height(),area.bottom)
                finally:other.close()
