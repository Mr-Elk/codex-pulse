"""Quota integration boundaries: persistence, portable bridge and native views."""
import copy
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock,patch

import overlay_settings
import overlay_style as style
from quota_backend import Bridge,persist_config,settings_path
from quota_model import selected_window,strip_values
from quota_service import QuotaService,clean_config
from test_quota import payload


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'settings.json'

    def test_quota_preserves_other_settings_and_ordinary_settings_preserve_quota(self):
        self.path.write_text(json.dumps({'theme_color':'#b58018','font_size':13,'unknown':{'keep':1}}))
        cfg=clean_config({'hours':168,'window':'secondary','reminder':{'enabled':True,'threshold':17}})
        persist_config(self.path,cfg)
        overlay_settings.save(self.path,17,None,True,['recent','quota','tokens'])
        data=json.loads(self.path.read_text())
        self.assertEqual(data['quota'],cfg);self.assertEqual(data['unknown'],{'keep':1})
        self.assertEqual(data['theme_color'],'#b58018')
        self.assertEqual(overlay_settings.load(self.path)['visible_metrics'],['recent','quota','tokens'])

    def test_missing_selected_window_never_silently_uses_another_window(self):
        state=payload();cfg=clean_config({'window':'secondary'})
        self.assertIsNone(selected_window(state,cfg))
        self.assertEqual(strip_values(state,cfg,1001)['quota'],'—')

    def test_corrupt_history_does_not_stop_official_quota_or_expose_raw_source(self):
        history=self.path.with_name('quota-history.sqlite3');history.write_text('not a database')
        source=Mock();source.read.return_value={'account_id':'private-id','limits':{'rateLimits':{'primary':{'usedPercent':25}}}}
        states=[];service=QuotaService(history,None,states.append,source)
        state=service.read_once()
        self.assertEqual(state['status'],'ready');self.assertIn('history_error',state)
        self.assertNotIn('private-id',json.dumps(states));self.assertEqual(states[-1]['groups'][0]['windows'][0]['remaining'],75)

    def test_bridge_blocks_redemption_and_requires_local_history_confirmation(self):
        bridge=Bridge(self.path,lambda _:None,Mock())
        for msg in ({'method':'account/rateLimitResetCredit/consume'},{'method':'history/clear'}):
            with self.assertRaises(ValueError):bridge.request(msg)
        result=bridge.request({'method':'configure','config':{'hours':6}})
        self.assertEqual(result['config']['hours'],6)
        self.assertTrue(bridge.request({'method':'history/clear','confirmed':True})['accepted'])
        with patch('sys.platform','darwin'):
            self.assertIn('Library/Application Support/CodexPulse',settings_path().as_posix())

    def test_range_changes_recompute_history_without_an_extra_official_read(self):
        source=Mock();source.read.return_value={'account_id':'one','limits':{'rateLimits':{'primary':{'usedPercent':20,'resetsAt':time.time()+1000}}}}
        updated=threading.Event();states=[]
        def emit(state):
            states.append(state)
            if state.get('recent',{}).get('hours')==6:updated.set()
        service=QuotaService(self.path.with_suffix('.db'),None,emit,source)
        try:
            service.start()
            deadline=time.monotonic()+2
            while not states and time.monotonic()<deadline:threading.Event().wait(.01)
            self.assertTrue(states)
            service.configure({'hours':6})
            self.assertTrue(updated.wait(2));self.assertEqual(source.read.call_count,1)
            service.clear_history()
        finally:
            service.close();service.thread.join(2)
        self.assertFalse(service.thread.is_alive())


class NativeQuotaTests(unittest.TestCase):
    def test_reminder_cancel_invalid_input_and_save(self):
        from test_panel_layout import PanelLayoutTests
        from quota_panel import reminder_dialog
        import tkinter as tk
        def descendants(widget):
            result=[]
            for child in widget.winfo_children():result.append(child);result.extend(descendants(child))
            return result
        with PanelLayoutTests().panel() as (panel,root,_):
            owner=panel.owner;owner.quota_preferences=clean_config(None);owner.quota_snapshot=payload(at=time.time())
            owner.configure_quota=Mock()
            dialog=reminder_dialog(panel);root.update()
            widgets=descendants(dialog)
            entry=next(w for w in widgets if type(w) is tk.Entry);entry.delete(0,'end');entry.insert(0,'101')
            save=next(w for w in widgets if isinstance(w,tk.Button) and w.cget('text')=='保存')
            cancel=next(w for w in widgets if isinstance(w,tk.Button) and w.cget('text')=='取消')
            save.invoke();root.update();owner.configure_quota.assert_not_called();self.assertTrue(dialog.winfo_exists())
            cancel.invoke();root.update();owner.configure_quota.assert_not_called();self.assertFalse(panel.modal_open)
            dialog=reminder_dialog(panel);root.update();widgets=descendants(dialog)
            entry=next(w for w in widgets if type(w) is tk.Entry);entry.delete(0,'end');entry.insert(0,'17')
            next(w for w in widgets if isinstance(w,tk.Button) and w.cget('text')=='保存').invoke();root.update()
            self.assertEqual(owner.configure_quota.call_args.args[0]['reminder']['threshold'],17)
            self.assertFalse(panel.modal_open)

    def test_account_views_ranges_and_theme_keep_state_separate(self):
        from test_panel_layout import PanelLayoutTests
        import theme
        for scale in (1,1.5):
            with PanelLayoutTests().panel(scale=scale,tab='quota') as (panel,root,area):
                owner=panel.owner;page=panel.quota_page
                self.assertEqual(len(page.rows),len(owner.quota_snapshot["groups"][0]["windows"]))
                original=copy.deepcopy(owner.quota_preferences)
                page.change_view('usage');root.update()
                self.assertFalse(page.expanded)
                page.change_analysis('hours',17);root.update()
                self.assertEqual(owner.quota_preferences,original)
                page.toggle_records();root.update();self.assertTrue(page.expanded)
                from settings_panel import VectorButton
                with patch.object(VectorButton,'focus_set') as focus:
                    page.change_view('overview');root.update();focus.assert_called_once()
                page.change_view('credits');root.update();self.assertIn('count',page.widgets)
                page.change_view('overview');root.update()
                previous=theme.current();theme.activate('#36824b');panel.apply_theme(previous);root.update()
                owner.quota_snapshot={'status':'unavailable','groups':[],'message':'身份待确认'}
                page.refresh();root.update();self.assertEqual(page.rows,[])
                self.assertIn('身份待确认',page.widgets['status'].cget('text'))
                panel.show_tab('strip');root.update();self.assertEqual(len(panel.metric_toggles),9)

    def test_nine_metric_rendering_folds_whole_fields_at_each_scale(self):
        from strip_renderer import render
        from test_strip_renderer import SNAPSHOT,decode_png
        state=payload(at=time.time());w=state['groups'][0]['windows'][0]
        state['recent']={'spent':130.25,'partial':True,'scope':{'account':state['account_key'],'window':w['key'],'basis':w['basis'],'hours':168}}
        snapshot={**SNAPSHOT,'visible_metrics':style.ALL_ORDER,'quota_display':strip_values(state,clean_config({'hours':168}),time.time())}
        for scale in (1,1.5,2):
            for width in (430,900,2100):
                png,layout=render(snapshot,round(width*scale),scale)
                self.assertTrue(layout)
                self.assertIn('recent',[cell['key'] for cell in layout])
                self.assertEqual(decode_png(png)[0][0],round(width*scale))
                for cell in layout:self.assertLessEqual(cell['text_right'],cell['right']-9)
        missing=dict(snapshot,available=False)
        self.assertEqual('130%', ''.join(run.text for run in style.metrics(missing)['recent'].runs))


if __name__=='__main__':unittest.main()
