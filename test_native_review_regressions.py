"""Regressions found by operating and capturing the real v19 review window."""
import tkinter as tk
import unittest
from unittest.mock import Mock
import test_panel_layout as fixture
from product_controls import Select
from product_panel import select_all
from font_policy import widget_family as family

class NativeReviewRegressions(unittest.TestCase):
    def test_native_and_strip_resolve_the_same_real_font_face(self):
        import ctypes as c
        import font_policy
        import strip_renderer
        from tkinter import font
        self.assertEqual(font_policy.family(),font_policy.widget_family())
        with fixture.PanelLayoutTests().panel() as (p,root,_):
            for weight in ('normal','bold'):
                face=font.Font(root=p.window,family=family(),size=-14,weight=weight)
                for character in ('A','数','7'):
                    actual=p.window.tk.call('font','actual',face,'--',character)
                    self.assertEqual(dict(zip(actual[::2],actual[1::2]))['-family'],family())
            get_name=strip_renderer.api.GdipGetFamilyName
            get_name.argtypes=[c.c_void_p,c.c_wchar_p,c.c_ushort];get_name.restype=c.c_int
            collection=strip_renderer.private_font_collection()
            for _ in range(3):
                renderer=strip_renderer.Renderer(200,1)
                try:
                    name=c.create_unicode_buffer(32)
                    self.assertEqual(get_name(renderer.family,name,0),0)
                    self.assertEqual(name.value,family())
                    self.assertIs(strip_renderer.private_font_collection(),collection)
                finally:renderer.close()
    def test_action_focus_uses_the_crisp_caption_and_keeps_one_tab_stop(self):
        from settings_panel import VectorButton
        with fixture.PanelLayoutTests().panel() as (p,root,_):
            button=VectorButton(p.body,'焦点检查',Mock(),1);button.pack();root.update()
            button.focus_force();root.update()
            self.assertEqual(button.focus_get(),button.normal_caption)
            self.assertIs(button.normal_caption.master,button.master)
            self.assertEqual(str(button.cget('takefocus')),'0')
            self.assertEqual(str(button.normal_caption.cget('takefocus')),'1')
            button.configure(state='disabled');root.update()
            self.assertEqual(str(button.inactive_caption.cget('takefocus')),'0')
    def test_action_captions_preserve_font_and_block_input_across_visual_states(self):
        from settings_panel import VectorButton
        from types import SimpleNamespace
        import tkinter.font as font
        for scale in (1,1.25,1.5,2):
            root=tk.Tk();root.withdraw();action=Mock()
            try:
                button=VectorButton(root,'确认固定',action,scale);button.pack();root.update_idletasks()
                self.assertEqual(str(button.cget('default')),'disabled')
                original=button.normal_caption.cget('font')
                button.enter();self.assertEqual(button.normal_caption.cget('font'),original)
                button.key_press(None);button.configure(state='disabled');button.key_release(None)
                action.assert_not_called()
                button.configure(state='normal');button.key_press(None);button.key_release(None)
                action.assert_called_once();action.reset_mock()
                button.pointer_press(None)
                event=SimpleNamespace(x_root=button.winfo_rootx()-1,y_root=button.winfo_rooty()-1)
                button.pointer_release(event);action.assert_not_called()
                actual=font.Font(root=button,font=button.normal_caption.cget('font')).actual()
                self.assertEqual(actual['family'],family())
                self.assertGreaterEqual(button.draw_height,abs(actual['size']))
            finally:root.destroy()
    def test_primary_button_ink_is_legible_for_presets_and_pale_custom_colors(self):
        import theme
        for _,fill in (*theme.PRESETS,('light','#fff3c4'),('mid','#808080'),('dark','#121827')):
            fill=theme.action_fill(fill);ink=theme.action_ink(fill)
            def lum(value):return theme.luminance(tuple(int(value[i:i+2],16)/255 for i in (1,3,5)))
            a,b=sorted((lum(fill),lum(ink)))
            self.assertGreaterEqual((b+.05)/(a+.05),4.5,(fill,ink))
    def test_hover_numbers_keep_primary_ink_and_installed_font(self):
        from metric_tooltip import MetricTooltip
        from overlay_geometry import Rect
        import tkinter.font as font
        with fixture.PanelLayoutTests().panel() as (p,root,_):
            tip=MetricTooltip(p.owner)
            try:
                tip.show('quota',Rect(100,600,180,640));root.update_idletasks()
                self.assertEqual(tip.labels['reading'].main.cget('foreground'),'#233955')
                self.assertEqual(font.Font(root=tip.window,font=tip.labels['reading'].main.cget('font')).actual()['family'],family())
                self.assertEqual(tip.labels['body'].cget('foreground'),'#607088')
            finally:tip.close()
    def test_recent_hover_header_fits_full_text_at_supported_scales(self):
        from metric_tooltip import MetricTooltip
        from overlay_geometry import Rect
        import tkinter.font as font
        for scale in (1,1.5,2):
            with self.subTest(scale=scale),fixture.PanelLayoutTests().panel(scale) as (p,root,_):
                tip=MetricTooltip(p.owner)
                try:
                    for hours in (1,168):
                        p.owner.quota_preferences['hours']=hours
                        tip.show('recent',Rect(100,600,180,640));tip.window.update()
                        for key in ('title','status'):
                            label=tip.labels[key];glyphs=font.Font(root=tip.window,font=label.cget('font')).measure(label.cget('text'))
                            self.assertLessEqual(glyphs,label.winfo_width(),(scale,hours,key,label.cget('text')))
                finally:tip.close()

    def test_partial_recent_hover_chinese_copy_does_not_orphan_its_last_punctuation(self):
        from metric_tooltip import MetricTooltip
        from overlay_geometry import Rect
        from quota_model import normalize
        from quota_service import clean_config
        import tkinter.font as font
        import time
        for scale in (1,1.5,2):
            with self.subTest(scale=scale),fixture.PanelLayoutTests().panel(scale) as (p,root,_):
                now=time.time();state=normalize({'account_id':'fixture','limits':{'rateLimits':{'primary':{'usedPercent':49,'windowDurationMins':10080,'resetsAt':now+6000}}}},now)
                window=state['groups'][0]['windows'][0]
                state['recent_by_window']={window['key']:{'spent':3.9,'sample_count':3,'partial':True,'last_at':now,'rows':[],
                    'scope':{'account':state['account_key'],'window':window['key'],'basis':window['basis'],'hours':1}}}
                p.owner.quota_preferences=clean_config({'hours':1});p.owner.quota_snapshot=state;tip=MetricTooltip(p.owner)
                try:
                    tip.show('recent',Rect(100,600,180,640));tip.window.update();body=tip.labels['body']
                    self.assertIn('未记录的时段不计入',body.cget('text'))
                    line=font.Font(root=tip.window,font=body.cget('font')).metrics('linespace')
                    self.assertLessEqual(body.winfo_reqheight(),line*3+round(scale*2))
                finally:tip.close()

    def test_disabled_actions_keep_readable_captions_and_cannot_execute(self):
        from settings_panel import VectorButton
        for scale in (1,1.25,1.5,2):
            root=tk.Tk();root.withdraw();action=Mock()
            try:
                for quiet in (False,True):
                    button=VectorButton(root,'确认固定',action,scale,quiet=quiet)
                    button.pack();button.configure(state='disabled');root.update_idletasks()
                    caption=button.inactive_caption
                    self.assertEqual(caption.cget('text'),'确认固定')
                    self.assertEqual(caption.cget('foreground'),'#69788d')
                    self.assertEqual(caption.winfo_manager(),'place')
                    button.invoke();action.assert_not_called()
                    button.configure(state='normal');root.update_idletasks()
                    self.assertEqual(caption.winfo_manager(),'')
                    button.invoke();action.assert_called_once();action.reset_mock()
                    button.destroy()
            finally:root.destroy()
    def test_dialog_has_a_real_rounded_region_and_restores_its_parent(self):
        import ctypes as c
        from ctypes import wintypes as w
        from product_controls import hours_dialog,Select
        import native_windows as win
        with fixture.PanelLayoutTests().panel() as (p,root,_):
            dialog=hours_dialog(p,3,Mock());root.update()
            try:
                self.assertIsNot(dialog.tk,p.window.tk)
                self.assertTrue(p.window.attributes('-disabled'))
                gdi,user=c.WinDLL('gdi32'),win.user32
                gdi.CreateRectRgn.argtypes=[c.c_int]*4;gdi.CreateRectRgn.restype=w.HRGN
                gdi.PtInRegion.argtypes=[w.HRGN,c.c_int,c.c_int];gdi.PtInRegion.restype=w.BOOL
                gdi.DeleteObject.argtypes=[w.HGDIOBJ]
                user.GetWindowRgn.argtypes=[w.HWND,w.HRGN];user.GetWindowRgn.restype=c.c_int
                region=gdi.CreateRectRgn(0,0,1,1)
                try:
                    self.assertGreater(user.GetWindowRgn(p.window_shape.hwnd,region),0)
                    self.assertFalse(gdi.PtInRegion(region,3,3))
                    self.assertTrue(gdi.PtInRegion(region,20,20))
                    self.assertGreater(user.GetWindowRgn(dialog.pulse_card.hwnd,region),0)
                    self.assertFalse(gdi.PtInRegion(region,0,0))
                    self.assertTrue(gdi.PtInRegion(region,dialog.winfo_width()//2,dialog.winfo_height()//2))
                finally:gdi.DeleteObject(region)
                selector=Select(p,dialog.pulse_card.body,[(1,'一'),(2,'二')],1,Mock());selector.pack();root.update()
                popup=selector.open();root.update();self.assertIs(popup.tk,dialog.tk);selector.cancel()
            finally:dialog.cancel_value();root.update()
            self.assertFalse(p.window.attributes('-disabled'));self.assertFalse(p.modal_open)
    def test_pending_local_history_has_a_loading_state_and_keeps_account_status_separate(self):
        from product_data import recent_info
        import time
        state={'status':'ready','account_key':'a','observed_at':time.time(),'groups':[],'history_loading':True}
        value=recent_info(state,{},time.time())
        self.assertTrue(value['loading']);self.assertEqual(value['value'],'—')
        self.assertIn('正在读取',value['local']);self.assertIn('已更新',value['account'])
        self.assertNotIn('首次读取',' '.join(value['notes']))
    def test_long_source_balance_is_visible_without_shortening_or_inventing_units(self):
        import tkinter.font as font
        with fixture.PanelLayoutTests().panel(tab='quota') as (p,root,_):
            p.owner.quota_snapshot['groups'][0]['balance']={'value':'9225980000'}
            p.quota_page.refresh();root.update();w=p.quota_page.widgets;label=w['balance']
            self.assertEqual(label.cget('text'),'9,225,980,000')
            self.assertGreaterEqual(label.winfo_width(),font.Font(root=label,font=label.cget('font')).measure(label.cget('text')))
            self.assertEqual('余额单位暂未提供',w['balance_note'].cget('text'))
    def test_balance_is_a_grouped_integer_in_one_row_without_mutating_source(self):
        from quota_model import balance_text
        self.assertEqual(balance_text('0'),'0')
        self.assertEqual(balance_text('57009.9225980000'),'57,010')
        self.assertEqual(balance_text('2.5'),'3')
        self.assertEqual(balance_text(None),'—')
        self.assertEqual(balance_text('NaN'),'—')
        with fixture.PanelLayoutTests().panel(tab='quota') as (p,root,_):
            source={'value':'57009.9225980000'}
            p.owner.quota_snapshot['groups'][0]['balance']=source
            p.quota_page.refresh();root.update();w=p.quota_page.widgets
            self.assertEqual(source,{'value':'57009.9225980000'})
            self.assertEqual(w['balance'].cget('text'),'57,010')
            self.assertFalse(w['balance_layout'])
            self.assertEqual(w['balance'].cget('anchor'),'e')
    def test_tooltip_refresh_does_not_demote_its_existing_owner(self):
        from metric_tooltip import MetricTooltip
        from overlay_geometry import Rect
        with fixture.PanelLayoutTests().panel() as (p,root,_):
            tip=MetricTooltip(p.owner);p.owner.win.decorate_overlay.reset_mock()
            try:
                tip.show('quota',Rect(100,600,180,640))
                tip.show('quota',Rect(110,600,190,640))
                self.assertEqual(p.owner.win.decorate_overlay.call_count,1)
                p.owner.win.decorate_overlay.assert_called_once_with(tip.hwnd)
                self.assertTrue(tip.window.attributes('-topmost'))
                self.assertNotIn(p.owner.hwnd,[call.args[1] for call in p.owner.win.own_overlay.call_args_list])
                self.assertEqual(p.owner.win.show_without_focus.call_count,2)
                self.assertTrue(p.owner.win.show_without_focus.call_args_list[0].kwargs['raise_window'])
                self.assertFalse(p.owner.win.show_without_focus.call_args_list[1].kwargs['raise_window'])
                tip.hide();tip.show('quota',Rect(110,600,190,640))
                self.assertTrue(p.owner.win.show_without_focus.call_args.kwargs['raise_window'])
            finally:tip.close()
    def test_quota_percentages_are_integer_presentations_without_changing_source_values(self):
        from quota_model import quota_percent,used_percent
        window={'remaining':26.5,'used':73.5};original=dict(window)
        self.assertEqual(quota_percent(3.9),'4%');self.assertEqual(quota_percent(2.5),'3%')
        self.assertEqual(quota_percent(None),'—');self.assertEqual(quota_percent(130.4),'130%')
        self.assertEqual(quota_percent(window['remaining']),'27%');self.assertEqual(used_percent(window),'73%')
        self.assertEqual(window,original)
    def test_checkbox_and_saved_choice_stay_in_sync_across_separate_tk_roots(self):
        with fixture.PanelLayoutTests().panel() as (p,root,_):
            owner=p.owner
            def save():owner.visible_metrics=tuple(k for k in owner.metric_order if owner.metric_choices[k].get())
            owner.select_metrics=Mock(side_effect=save)
            self.assertIsNot(p.window.tk,root.tk)
            self.assertIs(p.metric_variables['tokens']._tk,p.window.tk)
            self.assertTrue(p.metric_variables['tokens'].get())
            p.metric_toggles['tokens'].invoke();root.update()
            self.assertFalse(owner.metric_choices['tokens'].get());self.assertNotIn('tokens',owner.visible_metrics)
            select_all(p);root.update()
            self.assertTrue(p.metric_variables['tokens'].get());self.assertIn('tokens',owner.visible_metrics)
            p.show_tab('display');p.show_tab('strip');root.update()
            self.assertTrue(p.metric_variables['tokens'].get())
    def test_dropdown_stays_above_floating_settings_and_restores_modal_state(self):
        with fixture.PanelLayoutTests().panel() as (p,root,_):
            selector=Select(p,p.body,[(1,'一'),(2,'二')],1,Mock())
            selector.pack();root.update();p.modal_open=False
            popup=selector.open();root.update()
            self.assertTrue(popup.attributes('-topmost'));self.assertTrue(p.modal_open)
            selector.cancel();root.update();self.assertFalse(p.modal_open);self.assertIsNone(selector.popup)
    def test_titles_use_the_installed_base_family_with_explicit_weight(self):
        with fixture.PanelLayoutTests().panel() as (p,root,_):
            actual=dict(zip(*(iter(p.brand_title.tk.call('font','actual',p.brand_title.cget('font'))),)*2))
            self.assertEqual(actual['-family'],family());self.assertEqual(actual['-weight'],'bold')

if __name__=='__main__':unittest.main()
