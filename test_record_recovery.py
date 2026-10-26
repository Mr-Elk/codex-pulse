"""Corrupt local rows must not block later valid usage or falsify request timing."""
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from pulse import Monitor
import test_pulse
from test_pulse import THREAD, record
from thread_catalog import recent


class RecordRecoveryTests(unittest.TestCase):
    setUp = test_pulse.SessionTests.setUp
    tearDown = test_pulse.SessionTests.tearDown
    write = test_pulse.SessionTests.write
    def test_malformed_optional_rows_do_not_block_later_usage(self):
        rows = [
            {"type":"event_msg","payload":{"type":"token_count","info":[1]}},
            {"type":"event_msg","payload":{"type":"task_started","turn_id":["bad"]}},
            {"type":"event_msg","payload":{"type":"task_complete","turn_id":{"bad":1}}},
            {**record(),"payload":{**record()["payload"],"response_id":["bad"]}},
            {**record(),"payload":{**record()["payload"],"turn_id":["bad"]}},
        ]
        self.write(*rows, record())
        for _ in range(2):
            result = self.monitor.snapshot()
            self.assertTrue(result["available"])
            self.assertEqual(result["requests"],1)
            self.assertEqual(result["usage"]["output_tokens"],100)
            self.assertEqual(result["rounds"],1)
            self.assertTrue(result["warnings"])

    def test_invalid_context_window_does_not_break_totals_or_invent_a_percent(self):
        self.write(record())
        self.monitor.snapshot()
        for value in ("bad", -1, 0, True, [], {"size":100}):
            with self.subTest(value=value):
                self.monitor.consume({"type":"task_started","payload":{"model_context_window":value}})
                result = self.monitor.snapshot()
                self.assertTrue(result["available"])
                self.assertIsNone(result["context_percent_estimate"])
                self.monitor.consume({"type":"token_count","payload":{"info":{"model_context_window":value}}})
                result = self.monitor.snapshot()
                self.assertTrue(result["available"])
                self.assertIsNone(result["context_percent_estimate"])
                self.assertTrue(result["warnings"])


class LogRotationTests(unittest.TestCase):
    def create(self,path,rows):
        with closing(sqlite3.connect(path)) as db, db:
            db.execute("CREATE TABLE logs(id INTEGER PRIMARY KEY, ts INTEGER, ts_nanos INTEGER, thread_id TEXT, target TEXT, feedback_log_body TEXT)")
            db.executemany("INSERT INTO logs VALUES(?,?,0,?,'feedback_tags','stream_request{turn_id=turn1}')",[(i,t,THREAD) for i,t in rows])

    def test_replaced_log_resumes_low_ids_and_does_not_duplicate_copied_rows(self):
        with tempfile.TemporaryDirectory() as folder:
            home=Path(folder);path=home/'logs_2.sqlite'
            self.create(path,[(100,1000)])
            monitor=Monitor(home,THREAD)
            monitor.read_starts()
            path.rename(home/'previous.sqlite')
            self.create(path,[(1,2000),(100,1000)])
            monitor.read_starts();monitor.read_starts()
            self.assertEqual(len(monitor.starts),2)
            self.assertEqual({s['time'] for s in monitor.starts},{1000,2000})
            self.assertFalse(monitor.log_issue)

    def test_table_reset_with_same_inode_resumes_and_distinct_starts_stay_ambiguous(self):
        with tempfile.TemporaryDirectory() as folder:
            home=Path(folder);path=home/'logs_2.sqlite'
            self.create(path,[(100,1000)])
            monitor=Monitor(home,THREAD);monitor.read_starts()
            with closing(sqlite3.connect(path)) as db, db:
                db.execute('DELETE FROM logs')
                db.executemany("INSERT INTO logs VALUES(?,?,0,?,'feedback_tags','stream_request{turn_id=turn1}')",[(1,2000,THREAD),(2,2000,THREAD)])
            monitor.read_starts()
            self.assertEqual(monitor.last_log_id,2)
            self.assertEqual(len(monitor.starts),3)
            from pulse import pair_requests
            paired=pair_requests([{'time':2001,'turn_id':'turn1','usage':{'output_tokens':100}}],monitor.starts)
            self.assertIsNone(paired[0]['tps'])


class IndexRecoveryTests(unittest.TestCase):
    def test_bad_index_lines_preserve_valid_catalog_and_later_display_name(self):
        with tempfile.TemporaryDirectory() as folder:
            home=Path(folder)
            with closing(sqlite3.connect(home/'state_5.sqlite')) as db, db:
                db.execute('CREATE TABLE threads(id TEXT,title TEXT,archived INTEGER,updated_at INTEGER)')
                db.execute("INSERT INTO threads VALUES(?,'fallback',0,1)",(THREAD,))
            data=b'\xff\n'+json.dumps({'id':['bad'],'thread_name':'bad'}).encode()+b'\n[1]\n'
            data+=(json.dumps({'id':THREAD,'thread_name':'正确的名称'},ensure_ascii=False)+'\n').encode('utf-8')
            path=home/'session_index.jsonl';path.write_bytes(data)
            self.assertEqual(recent(home),[{'id':THREAD,'title':'正确的名称'}])
            self.assertEqual(path.read_bytes(),data)


if __name__=='__main__':
    unittest.main()
