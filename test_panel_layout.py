"""Viewport behavior: one session-list scrollbar without clipping controls."""
from contextlib import contextmanager
from pathlib import Path
import tempfile
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
    def panel(self, scale=1, work_height=900, title="工作会话"):
        root=tk.Tk();root.withdraw();errors=[]
        root.report_callback_exception=lambda *args:errors.append(str(args[1]))
        owner=layering.YieldTests().window();owner.root=root;owner.scale=scale
        owner.display_mode="desktop";owner.render_strip=render;owner.snapshot=SNAPSHOT
        owner.metric_choices={key:tk.BooleanVar(root,value=True) for key in style.ORDER}
        owner.lock_choice=tk.BooleanVar(root,value=True);owner.follow_choice=tk.BooleanVar(root,value=True)
        owner.thread_choice=tk.StringVar(root,value="a");owner.close=Mock()
        owner.theme_color=theme.DEFAULT;owner.expanded_mode="composer";owner.bound_title=title
        area=Rect(0,0,round(1280*scale),round(work_height*scale))
        owner.win.work_area.return_value=area
        catalog=[{"id":"a" if i==0 else str(i),"title":f"测试工作 {i:03d}"} for i in range(227)]
        with tempfile.TemporaryDirectory() as folder:
            owner.args.codex_home=Path(folder);owner.args.settings_file=Path(folder)/"settings.json"
            with patch("panel_chrome.Chrome"),patch.object(tk.Tk,"lift"),\
                 patch.object(tk.Tk,"focus_force"),patch("thread_catalog.recent",return_value=catalog):
                panel=None
                try:
                    panel=SettingsPanel(owner,area.right-20,area.bottom-20,tab="session")
                    root.update()
                    yield panel,root,area
                    self.assertEqual(errors,[])
                finally:
                    if panel:panel.close()
                    root.update()
                    root.destroy();theme.activate(theme.DEFAULT)

    def record(self,panel,area,label):
        sample={"label":label,"scale":panel.scale,"work_height":area.height,
                "panel_height":panel.window.winfo_height(),"geometry":panel.window.geometry(),"viewport":panel.content.winfo_height(),
                "body":panel.body.winfo_reqheight(),"list_height":panel.choices.winfo_height(),
                "outer_scroll":panel.scroller.overflow,"list_scroll":panel.session_scroll.overflow}
        SAMPLES.append(sample)
        return sample

    def test_session_fits_normal_work_area_at_each_scale_and_long_titles(self):
        for scale in (1,1.25,1.5,2):
            for title in ("工作会话","较长的工作会话标题与需求梳理以及业务接口联调"*3):
                with self.subTest(scale=scale,long_title=len(title)>10),self.panel(scale,title=title) as (panel,root,area):
                    s=self.record(panel,area,"normal")
                    self.assertFalse(s["outer_scroll"])
                    self.assertTrue(s["list_scroll"])
                    self.assertLessEqual(s["body"],s["viewport"]+2)
                    self.assertGreaterEqual(s["list_height"],panel.px(96))
                    self.assertGreaterEqual(panel.window.winfo_y(),area.top)
                    self.assertLessEqual(panel.window.winfo_y()+s["panel_height"],area.bottom)
                    self.assertLessEqual(panel.choose_button.winfo_rooty()+panel.choose_button.winfo_height(),panel.content.winfo_rooty()+s["viewport"])

    def test_search_keeps_one_scroll_area_and_short_screen_remains_reachable(self):
        with self.panel() as (panel,root,area):
            for term in ("026","不存在的查询","", "013", ""):
                panel.search.set(term);root.update()
                s=self.record(panel,area,"search")
                self.assertFalse(s["outer_scroll"])
                self.assertEqual(panel.content.yview(),(0.,1.))
            panel.show_tab("strip");root.update()
            panel.show_tab("session");root.update()
            self.assertFalse(panel.scroller.overflow)
        with self.panel(scale=1.5,work_height=520) as (panel,root,area):
            s=self.record(panel,area,"short")
            self.assertLessEqual(s["panel_height"],area.height)
            self.assertGreaterEqual(s["list_height"],panel.px(96))
            self.assertTrue(s["outer_scroll"])
            panel.content.yview_moveto(1);root.update()
            self.assertLessEqual(panel.choose_button.winfo_rooty()+panel.choose_button.winfo_height(),panel.content.winfo_rooty()+panel.content.winfo_height()+2)
