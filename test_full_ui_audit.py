import copy,tempfile,unittest
from pathlib import Path
from unittest.mock import Mock
import tkinter as tk
import tkinter.font as font
import test_panel_layout as fixture
from overlay_geometry import Rect,place,remember_capsule
import overlay_settings as preferences

class FullUIAuditTests(unittest.TestCase):
    def test_action_bitmap_and_caption_follow_the_real_width_and_height(self):
        from settings_panel import VectorButton
        for scale in (1,1.25,1.5,2):
            with self.subTest(scale=scale),fixture.PanelLayoutTests().panel(scale) as (p,root,_):
                button=p.button(p.body,'恢复位置',Mock(),quiet=True);button.place(x=0,y=0,width=p.px(94),height=p.px(24));root.update()
                self.assertEqual((button.art.width(),button.art.height()),(button.winfo_width(),button.winfo_height()))
                self.assertEqual(button.variant,'text');self.assertFalse(button.outlined)
                for height in (32,24,36):
                    button.place_configure(height=p.px(height));root.update()
                    self.assertEqual(button.draw_height,button.winfo_height())
                    caption=button.normal_caption
                    self.assertGreaterEqual(caption.winfo_width(),font.Font(root=caption,font=caption.cget('font')).measure(caption.cget('text')))
                    self.assertGreaterEqual(caption.winfo_y(),0)
                    self.assertLessEqual(caption.winfo_y()+caption.winfo_height(),button.winfo_height())

    def test_page_actions_are_legible_and_do_not_crop_their_caption(self):
        from settings_panel import VectorButton
        from product_panel import toggle_theme
        for scale in (1,1.5,2):
            with self.subTest(scale=scale),fixture.PanelLayoutTests().panel(scale) as (p,root,_):
                for tab,view in [('strip','metrics'),('strip','capsule'),('strip','source'),('display',''),('quota','')]:
                    if view:p.strip_view=view
                    p.show_tab(tab);root.update()
                    if tab=='display':toggle_theme(p);root.update()
                    if tab=='quota':
                        button=p.quota_page.widgets['refresh_button']
                        self.assertEqual(button.variant,'icon');self.assertEqual(button.winfo_width(),p.px(32));self.assertEqual(button.winfo_height(),p.px(32));self.assertEqual(button.cget('text'),'刷新账户数据')
                    def walk(widget):
                        for child in widget.winfo_children():
                            if isinstance(child,VectorButton) and child.winfo_ismapped() and child.cget('text'):
                                self.assertLessEqual(int(child.tk.splitlist(child.cget('font'))[1]),-p.px(13))
                                caption=child.inactive_caption if child.cget('state')=='disabled' else child.normal_caption
                                self.assertGreaterEqual(caption.winfo_width(),font.Font(root=caption,font=caption.cget('font')).measure(caption.cget('text')))
                            walk(child)
                    walk(p.body)

    def test_pointer_actions_fire_once_and_disabled_captions_remain_inert(self):
        with fixture.PanelLayoutTests().panel() as (p,root,_):
            action=Mock();button=p.button(p.body,'刷新',action,kind='secondary');button.pack();root.update()
            for widget in (button,button.normal_caption):
                widget.event_generate('<ButtonPress-1>',x=5,y=5);widget.event_generate('<ButtonRelease-1>',x=5,y=5);root.update()
            self.assertEqual(action.call_count,2)
            button.configure(state='disabled');root.update()
            self.assertEqual(str(button.cget('state')),'disabled')
            self.assertTrue(button.disabled_face.winfo_ismapped())
            self.assertEqual((button.disabled_face.winfo_width(),button.disabled_face.winfo_height()),(button.draw_width,button.draw_height))
            self.assertEqual(button.disabled_face.cget('image'),str(button.art))
            button.inactive_caption.event_generate('<ButtonPress-1>',x=5,y=5);button.inactive_caption.event_generate('<ButtonRelease-1>',x=5,y=5);root.update()
            self.assertEqual(action.call_count,2)
            button.configure(state='normal');root.update()
            self.assertFalse(button.disabled_face.winfo_ismapped())

    def test_segment_control_has_one_tab_stop_and_the_specified_inner_corners(self):
        with fixture.PanelLayoutTests().panel() as (p,root,_):
            p.show_tab('display');root.update();segments=p.font_segments;segments.select(15);root.update()
            self.assertEqual([key for key,button in segments.buttons.items() if str(button.cget('takefocus'))=='1'],[15])
            self.assertGreaterEqual(min(segments.art.get(58,6)),250)
            segments.step(1,1);root.update()
            self.assertEqual([key for key,button in segments.buttons.items() if str(button.cget('takefocus'))=='1'],[17])

    def test_segment_pointer_release_only_activates_once_inside_the_target(self):
        from panel_widgets import Segmented
        with fixture.PanelLayoutTests().panel() as (p,root,_):
            action=Mock();segments=Segmented(p.body,[(1,'一'),(2,'二')],action,1,width=160,height=32);segments.pack();segments.select(1);root.update()
            button=segments.buttons[2]
            button.event_generate('<ButtonPress-1>',x=5,y=5);button.event_generate('<ButtonRelease-1>',x=5,y=5);root.update()
            action.assert_called_once_with(2)
            button.event_generate('<ButtonPress-1>',x=5,y=5);button.event_generate('<ButtonRelease-1>',x=-5,y=5);root.update()
            action.assert_called_once_with(2)

    def test_composer_capsule_defaults_left_and_expanded_placement_is_unchanged(self):
        for scale in (1,1.25,1.5,2):
            window=Rect(-1000,0,round(1400*scale),round(1200*scale));composer=Rect(round(200*scale),round(900*scale),round(1000*scale),round(1000*scale))
            manual={'anchor':'composer','center_ratio':.62,'gap':19};original=copy.deepcopy(manual)
            expanded=place(window,round(650*scale),round(40*scale),composer,manual,scale)
            capsule=place(window,round(180*scale),round(40*scale),composer,manual,scale,capsule=True)
            self.assertEqual(capsule.left,composer.left+round(24*scale));self.assertEqual(capsule.bottom,expanded.bottom)
            self.assertEqual(manual,original)
            self.assertEqual(place(window,round(650*scale),round(40*scale),composer,manual,scale),expanded)

    def test_capsule_drag_persists_without_overwriting_the_expanded_anchor(self):
        window=Rect(0,0,1600,1000);composer=Rect(300,800,1100,900)
        manual={'anchor':'composer','center_ratio':.65,'gap':19}
        moved=Rect(500,741,680,781)
        result=remember_capsule(window,moved,manual,composer=composer)
        self.assertEqual(result['center_ratio'],.65)
        self.assertEqual(place(window,180,40,composer,result,capsule=True),moved)
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'settings.json';preferences.save(path,15,result)
            self.assertEqual(preferences.load(path)['position'],result)
        invalid={**manual,'capsule_left_ratio':float('nan')}
        self.assertEqual(preferences.valid_position(invalid),manual)

if __name__=='__main__':unittest.main()
