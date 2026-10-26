"""Minimal account-hashed snapshots, fourteen-day retention and honest coverage."""
from contextlib import contextmanager
import sqlite3
from quota_records import aggregate_records,bucket_minutes


class QuotaHistory:
    MAX_GAP=120

    def __init__(self,path):
        self.path=path
        path.parent.mkdir(parents=True,exist_ok=True)
        with self.connection() as db:
            db.execute('CREATE TABLE IF NOT EXISTS samples(account TEXT, win TEXT, basis TEXT, at REAL, used REAL, reset REAL, PRIMARY KEY(account,win,basis,at))')
            db.execute('CREATE TABLE IF NOT EXISTS reminders(key TEXT PRIMARY KEY, at REAL)')

    @contextmanager
    def connection(self):
        db=sqlite3.connect(str(self.path),timeout=3)
        try:
            with db:yield db
        finally:db.close()

    def record(self,state):
        if state.get('status')!='ready':return
        with self.connection() as db:
            for group in state['groups']:
                for w in group['windows']:
                    db.execute('INSERT OR IGNORE INTO samples VALUES(?,?,?,?,?,?)',(state['account_key'],w['key'],w['basis'],state['observed_at'],w['used'],w['resets_at']))
            db.execute('DELETE FROM samples WHERE at<?',(state['observed_at']-14*86400,))
            db.execute('DELETE FROM reminders WHERE at<?',(state['observed_at']-14*86400,))

    def recent(self,account,window,hours,now):
        start=now-hours*3600
        with self.connection() as db:
            rows=db.execute('SELECT at,used,reset FROM samples WHERE account=? AND win=? AND basis=? AND at>=? AND at<=? ORDER BY at',
                (account,window['key'],window['basis'],start-self.MAX_GAP,now)).fetchall()
        spent=0.;coverage=0.;valid=0;issues=[];details=[]
        for a,b in zip(rows,rows[1:]):
            if b[0]<start:continue
            elapsed=b[0]-a[0]
            if elapsed<=0:continue
            delta=None;note=''
            if elapsed>self.MAX_GAP:note='记录中断，未补算'
            elif a[0]<start:note='区间起点不完整，未补算'
            elif a[2] is None or b[2] is None:note='缺少周期信息，未计入'
            elif a[2]==b[2] and b[1]>=a[1]:delta=b[1]-a[1]
            elif b[2]>a[2] and b[0]>=a[2]:delta=b[1];note='跨重置边界，仅计入确认后的用量'
            else:note='额度修正或口径变化，未计入'
            if delta is not None:
                spent+=delta;valid+=1
                if not note:coverage+=elapsed
            if note:issues.append(note)
            details.append({'start':a[0],'at':b[0],'spent':delta,'note':note})
        tail=not rows or now-rows[-1][0]>self.MAX_GAP
        partial=coverage<hours*3600*.98 or bool(issues) or tail
        return {'spent':round(spent,2) if valid else None,'coverage_seconds':round(coverage),'hours':hours,
            'scope':{'account':account,'window':window['key'],'basis':window['basis'],'hours':hours},
            'partial':partial,'sample_count':len(rows),'notes':list(dict.fromkeys(issues))[:4],
            'rows':aggregate_records(details,hours,now),'bucket_minutes':bucket_minutes(hours),
            'first_at':rows[0][0] if rows else None,'last_at':rows[-1][0] if rows else None}

    def claim_reminder(self,key,now):
        with self.connection() as db:
            return db.execute('INSERT OR IGNORE INTO reminders VALUES(?,?)',(key,now)).rowcount==1

    def clear(self):
        # Only called after the app's explicit local-history confirmation.
        with self.connection() as db:db.execute('DELETE FROM samples')
