import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from quota_model import normalize,strip_values
from quota_history import QuotaHistory
from quota_service import QuotaService,clean_config
from quota_source import CodexQuotaSource,QuotaSourceError


def payload(account='one',used=20,reset=10000,credits=None,at=1000,plan='pro'):
    return normalize({'account_id':account,'plan':plan,'limits':{'rateLimits':{'primary':{'usedPercent':used,'windowDurationMins':300,'resetsAt':reset}},'rateLimitResetCredits':credits}},at)


class QuotaModelTests(unittest.TestCase):
    def test_multi_group_is_authoritative_and_missing_windows_are_not_zero(self):
        raw={'account_id':'one','limits':{'rateLimits':{'primary':{'usedPercent':1}},'rateLimitsByLimitId':{
            'other':{'primary':{'usedPercent':48,'windowDurationMins':60},'secondary':None}}}}
        s=normalize(raw,1000);self.assertEqual(len(s['groups']),1)
        self.assertEqual(s['groups'][0]['id'],'other');self.assertEqual(len(s['groups'][0]['windows']),1)
        self.assertEqual(s['groups'][0]['windows'][0]['remaining'],52)
        self.assertIsNone(s['groups'][0]['windows'][0]['resets_at'])

    def test_account_id_required_and_only_its_hash_leaves_normalization(self):
        s=normalize({'account_id':None,'limits':{}},1000);self.assertEqual(s['status'],'unavailable')
        s=payload('private-account');self.assertEqual(len(s['account_key']),64)
        self.assertNotIn('private-account',str(s))

    def test_expiry_null_missing_and_count_only_are_distinct(self):
        s=payload(credits={'availableCount':4,'credits':None})
        self.assertEqual(s['credits'],{'count':4,'rows':None})
        rows=[{'status':'available','expiresAt':None},{'status':'available'},
              {'status':'available','expiresAt':900},{'status':'redeemed','expiresAt':900}]
        s=payload(credits={'availableCount':4,'credits':rows})
        r=s['credits']['rows'];self.assertTrue(r[0]['no_expiry']);self.assertFalse(r[1]['no_expiry'])
        self.assertIn('待确认',r[2]['label']);self.assertEqual(r[3]['label'],'已使用')
        self.assertEqual(s['credits']['count'],4)

    def test_past_reset_waits_and_same_account_stale_values_remain_marked(self):
        s=payload(reset=900);v=strip_values(s,clean_config(None),1001)
        self.assertTrue(v['pending']);self.assertEqual(v['reset'],'待确认')
        self.assertEqual(strip_values(s,clean_config(None),1201)['quota'],'80%')
        from product_data import tooltip
        self.assertEqual(tooltip('quota',{},s,clean_config(None),now=1201)['status'],'数据过期')

    def test_invalid_percent_is_missing_not_full(self):
        for value in (True,-1,float('nan'),None):
            self.assertEqual(payload(used=value)['groups'][0]['windows'],[])
        self.assertEqual(payload(used=150)['groups'][0]['windows'][0]['remaining'],0)

    def test_malformed_config_and_custom_boundaries(self):
        self.assertEqual(clean_config({'reminder':'bad'})['reminder']['enabled'],False)
        for h in (0,169,True):self.assertEqual(clean_config({'hours':h})['hours'],1)
        self.assertEqual(clean_config({'hours':168,'reminder':{'threshold':0}})['reminder']['threshold'],0)


class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.h=QuotaHistory(Path(self.temp.name)/'history.sqlite3')

    def record(self,used,at,reset=10000,account='one',plan='pro'):
        s=payload(account,used,reset,at=at,plan=plan);self.h.record(s);return s

    def recent(self,s,now):return self.h.recent(s['account_key'],s['groups'][0]['windows'][0],1,now)

    def test_first_sample_is_unknown_not_zero_then_accumulates_observed_increment(self):
        s=self.record(10,1000);self.assertIsNone(self.recent(s,1000)['spent'])
        s=self.record(13,1030);r=self.recent(s,1030)
        self.assertEqual(r['spent'],3);self.assertTrue(r['partial']);self.assertEqual(r['coverage_seconds'],30)
        self.h.record(s);self.assertEqual(self.recent(s,1030)['spent'],3)

    def test_accounts_and_plan_changes_do_not_mix(self):
        self.record(10,1000);s=self.record(99,1030,account='two')
        self.assertIsNone(self.recent(s,1030)['spent'])
        s=self.record(50,1060,plan='plus');self.assertIsNone(self.recent(s,1060)['spent'])

    def test_sleep_gap_and_negative_correction_are_not_fabricated_consumption(self):
        self.record(10,1000);self.record(50,1600);s=self.record(45,1630)
        r=self.recent(s,1630);self.assertIsNone(r['spent']);self.assertEqual(len(r['notes']),2)

    def test_confirmed_natural_reset_accumulates_segments_above_one_hundred(self):
        self.record(0,900,reset=1000);self.record(90,990,reset=1000)
        self.record(20,1020,reset=2000);s=self.record(40,1050,reset=2000)
        r=self.recent(s,1050);self.assertEqual(r['spent'],130);self.assertTrue(r['partial'])

    def test_early_deadline_change_without_confirmation_is_excluded(self):
        self.record(60,1000);s=self.record(2,1030,reset=20000)
        self.assertIsNone(self.recent(s,1030)['spent'])

    def test_missing_reset_and_account_clearing(self):
        self.record(20,1000,reset=None);s=self.record(30,1030,reset=None)
        self.assertIsNone(self.recent(s,1030)['spent'])
        self.h.clear();self.assertEqual(self.recent(s,1030)['sample_count'],0)


class ReminderTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.now=1000;self.source=Mock();self.events=[]
        self.cfg=clean_config({'reminder':{'enabled':True,'threshold':20,'source':'any'}})
        self.s=QuotaService(Path(self.temp.name)/'q.db',self.cfg,self.events.append,self.source,lambda:self.now)

    def state(self,used,account='one',reset=10000):return payload(account,used,reset,at=self.now)

    def test_low_at_enable_is_baseline_and_crossing_only_notifies_once_per_cycle(self):
        self.assertEqual(self.s.reminders(self.state(90),self.cfg,self.now),[])
        self.now+=30;self.assertEqual(self.s.reminders(self.state(70),self.cfg,self.now),[])
        self.now+=30;self.assertEqual(len(self.s.reminders(self.state(80),self.cfg,self.now)),1)
        self.now+=30;self.s.reminders(self.state(70),self.cfg,self.now)
        self.now+=30;self.assertEqual(self.s.reminders(self.state(90),self.cfg,self.now),[])

    def test_account_change_missing_data_and_long_gap_rebaseline(self):
        self.s.reminders(self.state(70),self.cfg,self.now)
        self.now+=30;self.assertEqual(self.s.reminders(self.state(90,'two'),self.cfg,self.now),[])
        self.now+=200;self.assertEqual(self.s.reminders(self.state(90),self.cfg,self.now),[])
        self.now+=30;self.assertEqual(self.s.reminders(self.state(95,reset=900),self.cfg,self.now),[])

    def test_unavailable_read_drops_display_and_does_not_use_previous_account(self):
        self.source.read.side_effect=QuotaSourceError('连接暂不可用')
        state=self.s.read_once();self.assertEqual(state['status'],'unavailable');self.assertEqual(state['groups'],[])

    def test_configuration_change_resets_baseline(self):
        self.s.previous={'old':(80,1000)};self.s.configure({'reminder':{'enabled':True,'threshold':10}})
        self.assertEqual(self.s.previous,{})


class SourceTests(unittest.TestCase):
    def test_client_allowlist_excludes_all_redemption_model_and_auth_mutations(self):
        s=CodexQuotaSource()
        for method in ('turn/start','account/rateLimitResetCredit/consume','account/login/start','account/logout'):
            with self.assertRaises(QuotaSourceError):s._request(method)

    def test_source_rejects_account_switch_during_read_and_workspace_mismatch(self):
        for after,routing in [('two',None),('one','wrong')]:
            s=CodexQuotaSource();s._start=Mock();s.close=Mock()
            def a(email):return {'account':{'type':'chatgpt','email':email,'planType':'pro'},'workspaceRouting':{'chatgptAccountId':routing} if routing else None}
            s._request=Mock(side_effect=[a('one'),{'accountId':'id','rateLimits':{}},a(after)])
            with self.assertRaises(QuotaSourceError):s.read()


if __name__=='__main__':unittest.main()
