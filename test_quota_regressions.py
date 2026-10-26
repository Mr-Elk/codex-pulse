"""Regression checks for actual range switching, reminder continuity and empty filters."""
import copy,json
from pathlib import Path
import subprocess,sys,tempfile,time,unittest
from unittest.mock import Mock

import overlay_style as style
from quota_model import normalize,strip_values
from quota_service import QuotaService,clean_config,load_config
from quota_backend import persist_config
from test_quota import payload


def two_windows(now,primary=33,secondary=58):
    return normalize({'account_id':'fixture','plan':'pro','limits':{'rateLimits':{
       'primary':{'usedPercent':primary,'windowDurationMins':300,'resetsAt':2_000_000_000},
       'secondary':{'usedPercent':secondary,'windowDurationMins':10080,'resetsAt':2_000_600_000}}}},now)


class QuotaRegressionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name);self.now=time.time();self.events=[]
        self.cfg=clean_config({'reminder':{'enabled':True,'source':'primary','threshold':20}})
        self.service=QuotaService(self.path/'q.db',self.cfg,self.events.append,Mock(),lambda:self.now)

    def with_history(self):
        for offset,a,b in ((-3660,10,40),(-3630,20,41),(-30,30,50),(0,33,58)):
            self.service.history.record(two_windows(self.now+offset,a,b))
        self.service.publish(two_windows(self.now))
        return copy.deepcopy(self.events[-1])

    def test_old_range_and_window_values_are_never_relabelled_as_the_new_selection(self):
        state=self.with_history()
        self.assertEqual('3%',strip_values(state,clean_config(None),self.now)['recent'])
        for cfg in (clean_config({'hours':6}),clean_config({'window':'secondary','hours':6})):
            self.assertEqual('—',strip_values(state,cfg,self.now)['recent'])

    def test_both_windows_are_computed_for_the_same_range(self):
        state=self.with_history();values=state.get('recent_by_window',{})
        self.assertEqual(sorted(r['spent'] for r in values.values()),[3,8])
        self.service.configure({'hours':3});self.service.publish(two_windows(self.now))
        values=self.events[-1]['recent_by_window']
        self.assertEqual(sorted(r['spent'] for r in values.values()),[9,13])

    def test_range_capsule_and_unrelated_focus_changes_do_not_drop_a_primary_reminder(self):
        self.service.reminders(payload(used=70,at=self.now,reset=self.now+500),self.cfg,self.now)
        cfg=copy.deepcopy(self.cfg);cfg.update(hours=24,capsule='task',window='secondary')
        self.service.configure(cfg);self.now+=30
        notices=self.service.reminders(payload(used=85,at=self.now,reset=self.now+470),cfg,self.now)
        self.assertEqual(len(notices),1)

    def test_enable_uses_a_fresh_reading_so_the_first_drop_is_not_missed(self):
        self.service.configure({'reminder':{'enabled':False}})
        self.service.publish(payload(used=70,at=self.now,reset=self.now+500))
        self.service.configure(self.cfg);self.now+=30
        notices=self.service.reminders(payload(used=85,at=self.now,reset=self.now+470),self.cfg,self.now)
        self.assertEqual(len(notices),1)

    def test_changed_rule_suppresses_an_already_queued_notification(self):
        from quota_service import reminder_rule
        old_rule=reminder_rule(self.cfg)
        self.service.configure({'reminder':{'enabled':False}})
        self.service.publish(payload(at=self.now),['old notification'],old_rule)
        self.assertNotIn('notifications',self.events[-1])

    def test_reminder_ledger_survives_a_new_service_instance(self):
        self.service.reminders(payload(used=70,at=self.now,reset=self.now+500),self.cfg,self.now)
        self.now+=30
        self.assertEqual(len(self.service.reminders(payload(used=85,at=self.now,reset=self.now+470),self.cfg,self.now)),1)
        other=QuotaService(self.path/'q.db',self.cfg,lambda _:None,Mock(),lambda:self.now)
        other.reminders(payload(used=70,at=self.now,reset=self.now+470),self.cfg,self.now)
        self.now+=30
        self.assertEqual(other.reminders(payload(used=85,at=self.now,reset=self.now+440),self.cfg,self.now),[])

    def test_settings_survive_a_new_python_process_without_losing_theme_or_font(self):
        path=self.path/'settings.json';path.write_text(json.dumps({'font_size':13,'theme_color':'#3f78db'}))
        cfg=clean_config({'hours':17,'window':'secondary','reminder':{'enabled':True,'source':'any','threshold':25}})
        persist_config(path,cfg)
        child=subprocess.run([sys.executable,'-X','utf8','-B','-c',
             'import json,sys;from pathlib import Path;from quota_service import load_config;print(json.dumps(load_config(Path(sys.argv[1]))))',str(path)],
             capture_output=True,text=True,encoding='utf-8',timeout=5)
        self.assertEqual(child.returncode,0,child.stderr);self.assertEqual(json.loads(child.stdout),cfg)
        self.assertEqual(json.loads(path.read_text())['theme_color'],'#3f78db')

    def test_explicit_empty_metric_selection_remains_empty_after_reload_and_renders_controls(self):
        import overlay_settings
        from strip_renderer import render
        path=self.path/'settings.json';overlay_settings.save(path,15,None,True,[])
        self.assertEqual(overlay_settings.load(path)['visible_metrics'],[])
        self.assertEqual(style.normalize_keys([]),())
        png,cells=render({'visible_metrics':[]},style.width_for([]))
        self.assertEqual(cells,[]);self.assertGreater(len(png),1000)


class NativeControlRegressionTests(unittest.TestCase):
    def test_filled_selector_keeps_its_surface_width_when_the_label_changes(self):
        import tkinter as tk
        from settings_panel import VectorButton
        root=tk.Tk();root.withdraw()
        try:
            frame=tk.Frame(root,width=320,height=80);frame.pack_propagate(False);frame.pack()
            button=VectorButton(frame,'跟随统计条关注窗口',lambda:None,1)
            button.pack(fill='x');root.deiconify();root.update()
            button.configure(text='5 小时额度');root.update_idletasks()
            self.assertEqual(button.art.width(),button.winfo_width())
        finally:root.destroy()


if __name__=='__main__':unittest.main()
