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
    def test_display_theme_and_custom_drafts_keep_the_native_window(self):
        from test_panel_layout import PanelLayoutTests
        with PanelLayoutTests().panel(tab='display') as (panel,root,area):
            owner=panel.owner;identity=panel.window.winfo_id()
            panel.theme_open=True;panel.show_tab('display');root.update()
            for seed in [value for _,value in theme.PRESETS]+['#225599']:
                owner.set_theme_color(seed);root.update()
                self.assertEqual(panel.window.winfo_id(),identity)
                self.assertEqual([value for value,button in panel.theme_buttons.items() if button.selected],[seed] if seed in panel.theme_buttons else [])
                self.assertEqual(panel.color_editor.value.get(),seed.upper())
                for button in panel.mode_buttons.values():
                    left,_,right,_=button.bbox('mode-title')
                    self.assertLessEqual(right,button.winfo_width());self.assertGreater(left,0)
            editor=panel.color_editor;before=owner.theme_color
            editor.value.set('#168578');self.assertEqual(owner.theme_color,before)
            editor.cancel();self.assertEqual(editor.value.get(),before.upper())
            editor.value.set('#oops');editor.apply();self.assertEqual(owner.theme_color,before)
            editor.value.set('#168578');editor.apply();root.update()
            self.assertEqual(owner.theme_color,'#168578');self.assertEqual(theme.load(owner.args.settings_file),'#168578')
            for size in (13,15,17,13):panel.change_font(size);self.assertEqual(owner.font_size,size)
            for mode in ('composer','desktop','composer'):
                panel.change_mode(mode);self.assertEqual(owner.display_mode,mode)

if __name__=='__main__':unittest.main()
