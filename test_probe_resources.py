"""Behavioral tests for the locator's bounded process lifetime and protocol."""
import json
import subprocess
import sys
import time
import unittest
from unittest.mock import patch
from context_probe import PersistentProbe


class ProbeResourceTests(unittest.TestCase):
    def helper(self, **options):
        children=[]
        value={"composer":{"left":10,"top":100,"right":500,"bottom":200},
               "composer_source":"named","chat_title":"A","chat_status":"ok","interaction_open":False}
        def command(hwnd):
            reply={**value,"chat_title":str(hwnd),"probe_private_bytes":options.pop("reported_bytes",0)}
            program="import sys,json\nfor line in sys.stdin:\n print("+repr(json.dumps(reply))+",flush=True)\n"
            return [sys.executable,"-u","-c",program]
        probe=PersistentProbe(command_factory=command,**{k:v for k,v in options.items() if k!='reported_bytes'})
        real_start=probe.start
        def start(hwnd):
            real_start(hwnd);children.append(probe.process)
        probe.start=start
        self.addCleanup(probe.close)
        return probe,children

    def test_request_rotation_delivers_every_observation_and_reaps_old_children(self):
        probe,children=self.helper(max_requests=2)
        observations=[probe.read(100) for _ in range(7)]
        self.assertTrue(all(v==observations[0] for v in observations))
        self.assertEqual(observations[0][1:],('100','ok',False))
        self.assertEqual((probe.starts,probe.requests,probe.recycles),(4,7,3))
        self.assertTrue(all(p.poll() is not None for p in children[:-1]))
        self.assertEqual(probe.metadata,{'page_kind':'work','composer_status':'found'})

    def test_age_rotation_requires_no_setting_or_identity_change(self):
        clock=[10.0]
        probe,children=self.helper(max_age=5,clock=lambda:clock[0])
        first=probe.read(100);clock[0]+=6
        self.assertEqual(probe.read(100),first)
        self.assertEqual(probe.last_recycle_reason,'age')
        self.assertIsNotNone(children[0].poll())

    def test_memory_ceiling_rotates_only_after_returning_valid_response(self):
        probe,children=self.helper(reported_bytes=170*1024*1024)
        first=probe.read(100)
        self.assertIsNone(children[0].poll())
        self.assertEqual(probe.read(100),first)
        self.assertEqual(probe.last_recycle_reason,'memory')
        self.assertIsNotNone(children[0].poll())

    def test_brief_timeout_keeps_one_request_but_stalled_request_is_replaced(self):
        clock=[10.0];starts=[]
        def factory(hwnd):
            delay=0.3 if not starts else 0
            starts.append(delay)
            code=f"import sys,time,json\nfor line in sys.stdin:\n time.sleep({delay})\n print(json.dumps({{'chat_title':'A','chat_status':'ok','interaction_open':False}}),flush=True)\n"
            return [sys.executable,'-u','-c',code]
        probe=PersistentProbe(command_factory=factory,clock=lambda:clock[0],request_deadline=15)
        try:
            self.assertEqual(probe.read(100,timeout=.005)[2],'unavailable')
            old=probe.process
            clock[0]=11
            self.assertEqual(probe.read(100,timeout=.005)[2],'unavailable')
            self.assertEqual((probe.starts,probe.requests),(1,1))
            clock[0]=26
            self.assertEqual(probe.read(100)[1:],('A','ok',False))
            self.assertEqual((probe.starts,probe.requests),(2,2))
            self.assertIsNotNone(old.poll())
            self.assertEqual(probe.last_recycle_reason,'stalled')
        finally:probe.close()

    def test_old_window_response_cannot_cross_a_rotation(self):
        probe,_=self.helper(max_requests=1)
        self.assertEqual(probe.read(100)[1],'100')
        self.assertEqual(probe.read(200)[1],'200')
        self.assertEqual(probe.read(100)[1],'100')

    def test_exit_between_poll_and_write_retries_only_one_fresh_request(self):
        probe,children=self.helper()
        probe.start(100);old=probe.process
        old.stdin.close();old.wait(timeout=3)
        # Simulate the poll/write race, retaining the actual closed child pipe.
        with patch.object(old,'poll',return_value=None):
            # close() must still observe that wait/termination has reaped it.
            original_start=probe.start
            def restart(hwnd):
                old.poll=type(old).poll.__get__(old)
                original_start(hwnd)
            probe.start=restart
            self.assertEqual(probe.read(100)[1:],('100','ok',False))
        self.assertEqual(probe.requests,1)
        self.assertEqual(len(children),2)


if __name__=='__main__':unittest.main()
