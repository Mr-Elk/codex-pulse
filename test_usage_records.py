import copy,tempfile,unittest
from datetime import datetime
from pathlib import Path
from quota_records import aggregate_records,bucket_minutes,record_percent,record_range
from quota_history import QuotaHistory
from test_quota import payload

def stamp(text):return datetime.fromisoformat(text).timestamp()

class UsageRecordTests(unittest.TestCase):
    def test_whole_hour_uses_every_sample_and_conserves_the_total(self):
        start=stamp('2026-10-24T01:00:00')
        with tempfile.TemporaryDirectory() as d:
            history=QuotaHistory(Path(d)/'history.sqlite')
            for i in range(121):
                state=payload(used=20+i*.1,reset=start+86400,at=start+i*30)
                history.record(state)
            report=history.recent(state['account_key'],state['groups'][0]['windows'][0],1,start+3600)
        self.assertEqual(report['sample_count'],121)
        self.assertEqual(report['spent'],12)
        self.assertEqual(len(report['rows']),4)
        self.assertAlmostEqual(sum(x['spent'] for x in report['rows']),report['spent'])
        self.assertTrue(all(not x['partial'] for x in report['rows']))
        self.assertEqual(report['rows'][0]['start'],start)
        self.assertEqual(report['rows'][-1]['at'],start+3600)

    def test_partial_coverage_missing_and_zero_remain_distinct(self):
        now=stamp('2026-10-24T01:45:00')
        details=[{'start':now-1800,'at':now-1770,'spent':0.,'note':''},
                 {'start':now-1770,'at':now-1500,'spent':None,'note':'记录中断，未补算'},
                 {'start':now-1500,'at':now-1470,'spent':.04,'note':''},
                 {'start':now-900,'at':now,'spent':None,'note':'缺少周期信息，未计入'}]
        before=copy.deepcopy(details);rows=aggregate_records(details,1,now)
        self.assertEqual(details,before)
        self.assertAlmostEqual(sum(x['spent'] or 0 for x in rows),.04)
        self.assertTrue(rows[0]['partial']);self.assertIsNone(rows[-1]['spent'])
        self.assertEqual(record_percent(rows[0]['spent']),'<1%')
        self.assertEqual(record_percent(None),'—');self.assertEqual(record_percent(0),'0%')

    def test_reset_and_boundary_pairs_are_not_prorated_or_discarded(self):
        now=stamp('2026-10-24T01:30:00')
        pairs=[{'start':now-930,'at':now-890,'spent':5.,'note':'跨重置边界，仅计入确认后的用量'},
               {'start':now-890,'at':now-860,'spent':.2,'note':''}]
        rows=aggregate_records(pairs,1,now)
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['start'],now-930)
        self.assertEqual(rows[0]['spent'],5.2)
        self.assertTrue(rows[0]['partial'])
        self.assertEqual(record_percent(130.5),'131%')

    def test_short_ranges_do_not_repeat_the_same_minute_and_cross_days_are_explicit(self):
        a=stamp('2026-10-24T01:19:05');b=a+30
        label=record_range({'start':a,'at':b})
        self.assertIn('01:19:05',label);self.assertIn('01:19:35',label)
        label=record_range({'start':stamp('2026-10-23T23:59:00'),'at':stamp('2026-10-24T00:01:00')})
        self.assertIn('10月23日',label);self.assertIn('10月24日',label)

    def test_multiday_scope_is_bounded_without_hiding_any_consumption(self):
        now=stamp('2026-10-24T12:00:00');start=now-168*3600
        details=[{'start':start+i*60,'at':start+(i+1)*60,'spent':.001,'note':''} for i in range(168*60)]
        rows=aggregate_records(details,168,now)
        self.assertLessEqual(len(rows),8)
        self.assertAlmostEqual(sum(x['spent'] for x in rows),len(details)*.001)
        self.assertEqual(rows[0]['start'],start);self.assertEqual(rows[-1]['at'],now)
        self.assertEqual([bucket_minutes(h) for h in (1,3,6,12,24,72,168)],[15,30,30,60,180,360,1440])

if __name__=='__main__':unittest.main()
