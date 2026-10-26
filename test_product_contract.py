"""High-value v19 state, scope, migration and source regressions."""
import copy,tempfile,time,unittest
from pathlib import Path
from unittest.mock import Mock
from quota_model import normalize,strip_values
from quota_service import QuotaService,clean_config
from quota_source import QuotaSourceError
from product_data import recent_info,tooltip

class ProductContractTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.now=time.time()
        self.raw={'account_id':'fixture','plan':'pro','limits':{'rateLimits':{'primary':{'usedPercent':49,'windowDurationMins':10080,'resetsAt':self.now+3600},'credits':{'balance':'12.30','hasCredits':True,'unlimited':False}},'rateLimitResetCredits':{'availableCount':7,'credits':[{'status':'available','expiresAt':None}]}}}
        self.cfg=clean_config({'hours':3})
    def state(self):
        state=normalize(self.raw,self.now);w=state['groups'][0]['windows'][0]
        record={'spent':3.9,'sample_count':3,'partial':True,'last_at':self.now,'coverage_seconds':120,'rows':[],
          'scope':{'account':state['account_key'],'window':w['key'],'basis':w['basis'],'hours':3}}
        state['recent_by_window']={w['key']:record};return state
    def test_balance_is_independent_and_does_not_invent_a_currency(self):
        state=self.state();balance=state['groups'][0]['balance']
        self.assertEqual(balance['value'],'12.30');self.assertIsNone(balance['unit'])
        self.assertEqual(state['credits']['count'],7);self.assertEqual(len(state['credits']['rows']),1)
    def test_local_partial_and_account_stale_are_both_visible(self):
        state=self.state();state['status']='stale';state['observed_at']=self.now-600
        data=recent_info(state,self.cfg,self.now)
        self.assertEqual(data['value'],'4%');self.assertEqual(data['local'],'记录未覆盖全时段');self.assertIn('已过期',data['account'])
        hint=tooltip('recent',{},state,self.cfg,now=self.now)
        self.assertEqual(hint['status'],'本机估算');self.assertIn('本机记录',hint['foot']);self.assertIn('未记录的时段不计入',hint['body'])
        self.assertIn('上次额度估算',hint['body'])
    def test_no_confirmed_identity_masks_old_values_but_does_not_delete_history(self):
        state=self.state();state['status']='unavailable';state['account_key']=None
        self.assertEqual(recent_info(state,self.cfg,self.now)['value'],'—');self.assertEqual(strip_values(state,self.cfg,self.now)['quota'],'—')
        self.assertTrue(state['recent_by_window'])
    def test_weekly_primary_is_weekly_not_hardcoded_five_hours(self):
        state=self.state();self.assertEqual(state['groups'][0]['windows'][0]['name'],'7 天额度')
        data=recent_info(state,{**self.cfg,'window':'secondary'},self.now)
        self.assertIsNone(data['window']);self.assertEqual(data['value'],'—')
        self.assertEqual(strip_values(state,{**self.cfg,'window':'secondary'},self.now)['credits'],'7')
    def test_only_same_verified_account_failure_can_retain_a_stale_snapshot(self):
        source=Mock();source.read.return_value=self.raw;service=QuotaService(Path(self.temp.name)/'history.db',self.cfg,lambda _:None,source,lambda:self.now)
        first=service.read_once();source.read.side_effect=QuotaSourceError('暂不可用',first['account_key']);stale=service.read_once()
        self.assertEqual(stale['status'],'stale');self.assertEqual(stale['observed_at'],first['observed_at'])
        source.read.side_effect=QuotaSourceError('账户身份待确认');missing=service.read_once()
        self.assertEqual(missing['status'],'unavailable');self.assertEqual(missing['groups'],[])
        self.assertGreater(service.history.path.stat().st_size,0)
    def test_detail_scope_does_not_relabel_cached_history(self):
        state=self.state();self.assertEqual(recent_info(state,self.cfg,self.now)['value'],'4%')
        self.assertEqual(recent_info(state,{**self.cfg,'hours':17},self.now)['value'],'—')
    def test_capsule_does_not_allow_duplicate_or_unknown_metrics(self):
        c=clean_config({'capsule_primary':'quota','capsule_secondary':'quota'});self.assertIsNone(c['capsule_secondary'])
        c=clean_config({'capsule_primary':'tokens','capsule_secondary':None});self.assertEqual(c['capsule_primary'],'tokens');self.assertIsNone(c['capsule_secondary'])
    def test_capsule_all_presets_retain_both_metrics_after_pixel_rounding(self):
        from strip_renderer import render
        from overlay_style import COLUMN_WIDTHS,INSET
        state=self.state()
        for font in (13,15,17):
            for primary,secondary in [('quota','recent'),('tokens','speed'),('recent','reset'),('quota',None)]:
                cfg=clean_config({**self.cfg,'capsule_primary':primary,'capsule_secondary':secondary})
                keys=[k for k in (primary,secondary) if k];width=INSET+8+sum(COLUMN_WIDTHS[k] for k in keys)
                snap={'capsule':True,'font_size':font,'quota_config':cfg,'quota_state':state,'quota_display':strip_values(state,cfg,self.now)}
                png,cells=render(snap,round(width*font/15),font/15)
                self.assertEqual([c['key'] for c in cells],keys,(font,keys))
    def test_metrics_hover_does_not_depend_on_a_current_session(self):
        hint=tooltip('recent',{'available':False},self.state(),self.cfg,now=self.now)
        self.assertEqual(hint['value'],'4%');self.assertNotEqual(hint['status'],'暂无会话')

if __name__=='__main__':unittest.main()
