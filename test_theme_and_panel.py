"""Theme persistence and native widget interaction with no live user data."""
import json
from pathlib import Path
import tempfile
import tkinter as tk
import unittest
from unittest.mock import Mock, patch

import overlay_settings as preferences
import overlay_style as style
import test_layering as layering
from strip_renderer import render
from settings_panel import SettingsPanel
from overlay_geometry import Rect
from test_strip_renderer import SNAPSHOT, decode_png
import theme


def pixel(png,x,y):
    dimensions,rows=decode_png(png)
    width,height=dimensions[:2]
    offset=y*(width*4+1)+1+x*4
    return tuple(rows[offset:offset+4])


class ThemeTests(unittest.TestCase):
    def tearDown(self):
        theme.activate(theme.DEFAULT)

    def test_cached_vector_controls_follow_the_theme_and_restore_default(self):
        from svg_art import render_asset
        theme.activate(theme.DEFAULT)
        original=render_asset("toggle-on.svg",44,26)
        theme.activate("#168578")
        changed=render_asset("toggle-on.svg",44,26)
        self.assertNotEqual(original,changed)
        theme.activate(theme.DEFAULT)
        self.assertEqual(render_asset("toggle-on.svg",44,26),original)

    def test_invalid_theme_defaults_and_roundtrip_preserves_other_preferences(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/"settings.json"
            path.write_text(json.dumps({"version":2,"extra":{"keep":True},"theme_color":"not-a-color"}))
            self.assertEqual(theme.load(path),theme.DEFAULT)
            manual={"anchor":"composer","center_ratio":.3,"gap":16}
            display={"mode":"desktop","position":None,"compact":True,"animations":False,"expanded_mode":"composer"}
            preferences.save(path,17,manual,False,["speed","tokens"],display=display,theme_color="#2478B2")
            self.assertEqual(theme.load(path),"#2478b2")
            self.assertEqual(preferences.load(path)["position"],manual)
            self.assertEqual(preferences.load_display(path)["expanded_mode"],"composer")
            self.assertTrue(json.loads(path.read_text())["extra"]["keep"])
            path.write_text("[]")
            self.assertEqual(theme.load(path),theme.DEFAULT)

    def test_themes_change_color_without_moving_layout_or_changing_alpha(self):
        theme.activate(theme.DEFAULT)
        original,layout=render(SNAPSHOT,style.WIDTH)
        size,pixels=decode_png(original)
        alpha=lambda rows:bytes(rows[y*(size[0]*4+1)+1+x*4+3] for y in range(size[1]) for x in range(size[0]))
        for seed in [value for _,value in theme.PRESETS[1:]]+["#ffcc00","#ffffff","#225599"]:
            theme.activate(seed)
            changed,new_layout=render(SNAPSHOT,style.WIDTH)
            self.assertEqual(new_layout,layout)
            self.assertEqual(alpha(decode_png(changed)[1]),alpha(pixels))
            self.assertNotEqual(changed,original)
            text=theme.color("#7865d6")
            rgb=tuple(int(text[i:i+2],16)/255 for i in (1,3,5))
            self.assertGreaterEqual(1.05/(theme.luminance(rgb)+.05),4.5)
            self.assertEqual(theme.color(text),text)
        theme.activate(theme.DEFAULT)
        self.assertEqual(render(SNAPSHOT,style.WIDTH)[0],original)


class NativePanelTests(unittest.TestCase):
    def test_repeat_modes_selection_theme_changes_and_cancel_on_existing_window(self):
        root=tk.Tk();root.withdraw();errors=[]
        root.report_callback_exception=lambda *args:errors.append(str(args[1]))
        owner=layering.YieldTests().window();owner.root=root
        owner.display_mode="desktop"
        owner.render_strip=render;owner.snapshot=SNAPSHOT
        owner.metric_choices={key:tk.BooleanVar(root,value=True) for key in style.ORDER}
        owner.lock_choice=tk.BooleanVar(root,value=True)
        owner.follow_choice=tk.BooleanVar(root,value=True)
        owner.thread_choice=tk.StringVar(root,value="a")
        owner.close=Mock();owner.theme_color=theme.DEFAULT;owner.expanded_mode="composer"
        owner.win.work_area.return_value=Rect(0,0,1280,960)
        catalog=[{"id":"a","title":"工作 A"},{"id":"b","title":"工作 B"}]
        with tempfile.TemporaryDirectory() as folder:
            owner.args.codex_home=Path(folder);owner.args.settings_file=Path(folder)/"settings.json"
            with patch("panel_chrome.Chrome"),\
                 patch.object(tk.Tk,"lift"),patch.object(tk.Tk,"focus_force"),\
                 patch("thread_catalog.recent",return_value=catalog):
                panel=None
                try:
                    theme.activate("#c34c86")
                    panel=SettingsPanel(owner,700,760,tab="display");owner.settings_panel=panel
                    self.assertEqual(panel.tab,"display")
                    root.update()
                    for button in panel.mode_buttons.values():
                        for tag in ("mode-title","mode-description"):
                            left,_,right,_=button.bbox(tag)
                            self.assertLessEqual(abs((left+right)/2-button.winfo_width()/2),1)
                    self.assertIsNot(panel.window.tk,owner.root.tk)
                    self.assertEqual(panel.window.winfo_exists(),1)
                    owner.win.own_overlay.assert_called_with(panel.hwnd,None)
                    owner.win.set_floating.assert_called_with(panel.hwnd,True)
                    panel.show_tab("session")
                    for index in range(16):
                        mode="fixed" if index%2==0 else "auto"
                        panel.binding_modes.activate(mode)
                        self.assertEqual(owner.binding.mode,mode)
                        self.assertEqual(panel.binding_modes.selected,mode)
                    panel.binding_modes.activate("fixed")
                    self.assertEqual(panel.binding_status.cget("text"),"待选择")
                    panel.tree.selection_set("1");panel.selection_state();panel.choose_button.invoke()
                    self.assertEqual((owner.binding.mode,owner.binding.identity),("fixed","b"))
                    self.assertEqual(panel.choose_button.cget("state"),"disabled")
                    panel.show_tab("display")
                    window_id=panel.window.winfo_id()
                    for _ in range(3):
                        for seed in [value for _,value in theme.PRESETS]+["#225599"]:
                            panel.scroller.set(.2,.5)
                            panel.scroller.reveal()
                            if seed in panel.theme_buttons:
                                panel.theme_buttons[seed].invoke()
                            else:
                                owner.set_theme_color(seed)
                            width,height=decode_png(panel.scroller.thumb_png)[0][:2]
                            ink=panel.scroller.ink
                            # Narrow antialiased strokes can overshoot RGB a few
                            # levels during bicubic downsampling; their hue/opacity
                            # must still follow the active palette immediately.
                            self.assertTrue(all(abs(a-b)<=6 for a,b in zip(
                                pixel(panel.scroller.thumb_png,width//2,height//2)[:3],
                                tuple(int(ink[i:i+2],16) for i in (1,3,5)))))
                            self.assertGreaterEqual(pixel(panel.scroller.thumb_png,width//2,height//2)[3],250)
                            self.assertEqual((panel.scroller.first,panel.scroller.last),(.2,.5))
                            root.update()
                            self.assertEqual(panel.tab,"display")
                            self.assertEqual(panel.window.winfo_id(),window_id)
                            self.assertIn(seed.upper(),panel.theme_value.cget("text"))
                            self.assertEqual([value for value,button in panel.theme_buttons.items() if button.selected],
                                             [seed] if seed in panel.theme_buttons else [])
                            for value,button in panel.theme_buttons.items():
                                button.redraw()
                                self.assertEqual(pixel(button.png,15,18)[:3],
                                                 tuple(int(value[i:i+2],16) for i in (1,3,5)))
                                self.assertLessEqual(button.winfo_x()+button.winfo_width(),
                                                     button.master.winfo_width())
                            surfaces=[widget for widget in panel.body.winfo_children() if hasattr(widget,"fill")]
                            self.assertEqual([widget.fill for widget in surfaces],
                                             [theme.resolve(value,seed) for value in ("#f8f7fc","#faf9fd")])
                    before=owner.theme_color
                    editor=panel.color_editor
                    panel.choose_theme_color()
                    editor.value.set("#225599")
                    self.assertEqual(owner.theme_color,before)
                    editor.cancel()
                    self.assertEqual(owner.theme_color,before)
                    self.assertEqual(editor.value.get(),before.upper())
                    editor.value.set("#oops")
                    editor.apply()
                    self.assertEqual(theme.load(owner.args.settings_file),before)
                    self.assertIn("#RRGGBB",editor.status.cget("text"))
                    editor.value.set("#168578")
                    editor.apply_button.invoke()
                    self.assertEqual(owner.theme_color,"#168578")
                    self.assertEqual(theme.load(owner.args.settings_file),"#168578")
                    editor.toggle_picker();root.update()
                    editor.hue.step(1,0);editor.plane.step(-1,-1)
                    self.assertEqual(owner.theme_color,"#168578")
                    self.assertNotEqual(editor.value.get(),"#168578")
                    owner.set_theme_color("#3f78db")
                    self.assertEqual(editor.value.get(),"#3F78DB")
                    panel.show_tab("session")
                    panel.session_scroll.set(.1,.6)
                    owner.set_theme_color("#cd702b")
                    width,height=decode_png(panel.session_scroll.thumb_png)[0][:2]
                    ink=panel.session_scroll.ink
                    self.assertTrue(all(abs(a-b)<=6 for a,b in zip(
                        pixel(panel.session_scroll.thumb_png,width//2,height//2)[:3],
                        tuple(int(ink[i:i+2],16) for i in (1,3,5)))))
                    self.assertEqual((panel.session_scroll.first,panel.session_scroll.last),(.1,.6))
                    self.assertEqual(panel.binding_status.cget("text"),"已固定")
                    session_window=panel.window.winfo_id()
                    for seed in ("#36824b","#102fd9","#c34c86",theme.DEFAULT):
                        owner.set_theme_color(seed);root.update()
                        self.assertEqual(panel.window.winfo_id(),session_window)
                        self.assertEqual(panel.binding_modes.master.cget("bg"),theme.resolve("#faf9fd",seed))
                        self.assertEqual(panel.binding_status.master.cget("bg"),theme.resolve("#eee8fa",seed))
                        self.assertEqual(panel.binding_modes.buttons["auto"].cget("bg"),theme.resolve("#f3f1fa",seed))
                        self.assertEqual(panel.binding_modes.buttons["fixed"].cget("fg"),theme.resolve("#6f51cc",seed))
                        self.assertEqual(panel.binding_status.cget("fg"),theme.resolve("#7865d6",seed))
                        self.assertEqual(panel.binding_status.cget("text"),"已固定")
                    owner.binding=owner.binding.automatic().follow("工作 A",catalog)
                    owner.bound_title="工作 A"
                    panel.refresh()
                    for seed in ("#102fd9","#c34c86"):
                        owner.set_theme_color(seed);root.update()
                        self.assertEqual(panel.binding_status.cget("text"),"已识别")
                        self.assertEqual(panel.binding_status.cget("fg"),theme.resolve("#7865d6",seed))
                        self.assertEqual(panel.binding_status.master.cget("bg"),theme.resolve("#eee8fa",seed))
                    self.assertEqual(errors,[])
                finally:
                    if panel:panel.close()
                    root.update();root.destroy();theme.activate(theme.DEFAULT)


if __name__=="__main__":
    unittest.main()
