"""Shared Windows/macOS quota worker, configuration and threshold notifications."""
import copy
import json
import sqlite3
import threading
import time

from quota_history import QuotaHistory
from quota_model import normalize, selected_group, selected_window
from quota_source import CodexQuotaSource, QuotaSourceError

DEFAULTS={'group':None,'window':'primary','hours':1,'capsule':'quota','reminder':{'enabled':False,'source':'focus','threshold':20}}
METRIC_KEYS=('tokens','speed','context','cache','rounds','quota','recent','reset','credits')


def clean_config(value):
    value=value if isinstance(value,dict) else {};r=value.get('reminder');r=r if isinstance(r,dict) else {}
    hours=value.get('hours');threshold=r.get('threshold')
    primary=value.get('capsule_primary')
    if primary not in METRIC_KEYS:primary='tokens' if value.get('capsule')=='task' else 'quota'
    secondary=value.get('capsule_secondary') if 'capsule_secondary' in value else ('speed' if value.get('capsule')=='task' else 'recent')
    if secondary not in METRIC_KEYS or secondary==primary:secondary=None
    return {'group':value.get('group') if isinstance(value.get('group'),str) else None,
      'window':value.get('window') if value.get('window') in ('primary','secondary') else 'primary',
      'hours':hours if type(hours) is int and 1<=hours<=168 else 1,
      'capsule':value.get('capsule') if value.get('capsule') in ('quota','task') else 'quota',
      'capsule_primary':primary,'capsule_secondary':secondary,
      'reminder':{'enabled':r.get('enabled') is True,'source':r.get('source') if r.get('source') in ('focus','primary','secondary','any') else 'focus',
        'threshold':threshold if type(threshold) is int and 0<=threshold<=100 else 20}}


def load_config(path):
    try:return clean_config(json.loads(path.read_text(encoding='utf-8')).get('quota'))
    except (OSError,ValueError,AttributeError):return clean_config(None)


def reminder_rule(config):
    c=clean_config(config)
    return {'group':c['group'],'window':c['window'] if c['reminder']['source']=='focus' else None,'reminder':c['reminder']}


class QuotaService:
    def __init__(self,path,config,callback,source=None,clock=time.time):
        self.history_error=None
        try:self.history=QuotaHistory(path)
        except (OSError,sqlite3.Error):self.history=None;self.history_error='本机历史不可写；额度仍可读取，用量与提醒暂不可用'
        self.config=clean_config(config);self.callback=callback
        self.source=source or CodexQuotaSource();self.clock=clock
        self.stop_event=threading.Event();self.wake=threading.Event();self.lock=threading.Lock()
        self.last={};self.previous={};self.reminder_revision=0;self.thread=None
        self.force_read=True;self.clear_pending=False

    def start(self):
        self.thread=threading.Thread(target=self.run,daemon=True);self.thread.start()

    def configure(self,config):
        with self.lock:
            config=clean_config(config)
            if reminder_rule(config)!=reminder_rule(self.config):
                self.previous={};self.reminder_revision+=1
                # Use a confirmed, fresh visible reading as the enable/change
                # baseline. Waiting for the next poll can miss the first drop.
                now=self.clock();observed=self.last.get('observed_at')
                if (self.last.get('status')=='ready' and observed is not None and 0<=now-observed<=120
                        and not self.last.get('history_error')):
                    self.reminders(self.last,config,observed)
            self.config=config
        self.wake.set()

    def refresh(self):
        with self.lock:self.force_read=True
        self.wake.set()

    def clear_history(self):
        with self.lock:self.clear_pending=True
        self.wake.set()

    def publish(self,state,notices=None,notice_rule=None):
        with self.lock:config=copy.deepcopy(self.config)
        window=selected_window(state,config)
        state.pop('notifications',None)
        state.pop('recent',None)
        state.pop('notification_rule',None)
        state['recent_by_window']={}
        group=selected_group(state,config)
        if state.get('status') in ('ready','stale') and group and self.history:
            try:
                for w in group['windows']:
                    state['recent_by_window'][w['key']]=self.history.recent(state['account_key'],w,config['hours'],self.clock())
                if window:state['recent']=state['recent_by_window'].get(window['key'])
            except sqlite3.Error:self.history_error='本机历史读取失败；用量暂不可用'
        if self.history_error:state['history_error']=self.history_error
        self.last=state
        event=copy.deepcopy(state)
        if notices and notice_rule==reminder_rule(config):event.update(notifications=notices,notification_rule=notice_rule)
        self.callback(event)

    def reminders(self,state,config,now):
        r=config['reminder'];notices=[];group=selected_group(state,config)
        if not r['enabled'] or not group or not self.history:
            self.previous={}
            return notices
        focus=selected_window(state,config)
        active=set()
        for w in group['windows']:
            if r['source']=='focus' and (not focus or focus['key']!=w['key']):continue
            if r['source'] not in ('focus','any') and w['role']!=r['source']:continue
            if w['resets_at'] is None or w['reset_pending']:continue
            key=f"{state['account_key']}|{w['key']}|{w['basis']}|{w['resets_at']}|{r['threshold']}"
            active.add(key)
            previous=self.previous.get(key);self.previous[key]=(w['remaining'],now)
            if previous and 0<now-previous[1]<=120 and previous[0]>r['threshold']>=w['remaining']:
                if self.history.claim_reminder(key,now):notices.append(f"{group['name']} · {w['name']}剩余 {w['remaining']:g}%")
        self.previous={k:v for k,v in self.previous.items() if k in active}
        return notices

    def read_once(self):
        now=self.clock()
        notice_rule=None
        try:
            raw=self.source.read();now=self.clock();state=normalize(raw,now)
            if state.get('status')=='ready':
                try:
                    if self.history:self.history.record(state)
                    with self.lock:
                        config=copy.deepcopy(self.config)
                        notices=self.reminders(state,config,now)
                        notice_rule=reminder_rule(config)
                except sqlite3.Error:
                    notices=[];self.previous={};self.history_error='本机历史暂不可用；额度读取不受影响，提醒已暂停'
                state['notifications']=notices
            else:self.previous={}
        except (QuotaSourceError,OSError,ValueError) as error:
            self.previous={}
            confirmed=getattr(error,'account_key',None)
            if confirmed and confirmed==self.last.get('account_key') and self.last.get('groups'):
                state=copy.deepcopy(self.last);state.update(status='stale',checked_at=now,message='额度数据已过期，保留同一账户的上次读数')
            else:
                state={'status':'unavailable','identity_confirmed':False,'message':str(error) if isinstance(error,QuotaSourceError) else '本机额度记录暂不可用，请稍后刷新',
                       'observed_at':None,'groups':[],'credits':None}
        notices=state.pop('notifications',[])
        self.publish(state,notices,notice_rule)
        return state

    def run(self):
        next_read=0
        try:
            while not self.stop_event.is_set():
                self.wake.clear()
                with self.lock:
                    force,self.force_read=self.force_read,False
                    clear,self.clear_pending=self.clear_pending,False
                if clear and self.history:
                    try:self.history.clear();self.history_error=None
                    except sqlite3.Error:self.history_error='清除本机历史失败，请稍后重试'
                if force or time.monotonic()>=next_read:
                    self.read_once();next_read=time.monotonic()+30
                elif self.last:self.publish(copy.deepcopy(self.last))
                self.wake.wait(max(.1,next_read-time.monotonic()))
        finally:self.source.close()

    def close(self):
        self.stop_event.set();self.wake.set()
        # Closing our own stdin cancels outstanding reads without blocking Tk.
        self.source.close()
