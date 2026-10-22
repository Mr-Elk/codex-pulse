import gc
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock

from launch import supervise
from runtime_state import RuntimeSession, atomic_json, finish_child, health, process_identity, read_json, utc_now
from tk_lifetime import TkLifetime


class RuntimeTests(unittest.TestCase):
    def test_saved_running_flag_cannot_make_a_missing_process_live(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"runtime.json"
            atomic_json(p,{"pid":123,"running":True,"visible":True,"updated_at":utc_now()})
            result=health(p,lookup=lambda pid:{"alive":False,"reason":"process_missing"})
            self.assertFalse(result["running"])
            self.assertFalse(result["visible"])
            self.assertEqual(result["health_reason"],"process_missing")

    def test_reused_pid_and_stale_or_missing_heartbeat_are_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"runtime.json"
            session=RuntimeSession(p,"test")
            session.write({"running":True})
            state=read_json(p)
            state["process_created"]="original"
            atomic_json(p,state)
            self.assertEqual(health(p,lookup=lambda pid:{"alive":True,"created":"reused"})["health_reason"],"pid_reused")
            state.pop("process_created")
            atomic_json(p,state)
            self.assertEqual(health(p,lookup=lambda pid:{"alive":True},now=time.time()+30)["state"],"unresponsive")
            state.pop("updated_at")
            atomic_json(p,state)
            self.assertIsNone(health(p,lookup=lambda pid:{"alive":True})["running"])

    def test_actual_current_process_has_a_live_creation_identity(self):
        self.assertTrue(process_identity(os.getpid())["alive"])
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"runtime.json"
            s=RuntimeSession(p,"test");s.write({"running":True})
            self.assertEqual(health(p)["health_reason"],"live")
            s.finish("user_closed")
            self.assertEqual(read_json(p)["exit_reason"],"user_closed")
            self.assertFalse(health(p)["running"])

    def test_terminal_status_cannot_overwrite_a_newer_run(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"runtime.json"
            old=RuntimeSession(p,"old","old");new=RuntimeSession(p,"new","new")
            new.write({"running":True})
            old.finish("old_ended")
            self.assertFalse(finish_child(p,"old",7))
            self.assertEqual(read_json(p)["run_id"],"new")

    def test_supervisor_records_abrupt_child_exit_and_clears_running(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"runtime.json"
            script="import sys,os;sys.path.insert(0,"+repr(str(Path(__file__).parent))+");from runtime_state import RuntimeSession;RuntimeSession("+repr(str(p))+",'test','forced').write({'running':True});os._exit(23)"
            code=supervise([sys.executable,"-c",script],p,
                           run_id="forced",log_dir=Path(d)/"logs",version="test")
            self.assertEqual(code,23)
            state=read_json(p)
            self.assertFalse(state["running"])
            self.assertEqual(state["state"],"failed")
            self.assertEqual(state["exit_code"],23)
            self.assertTrue(state["supervisor_observed_exit"])

    def test_failed_launch_is_reported_and_corrupt_status_is_unavailable(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"runtime.json"
            with self.assertRaises(OSError):
                supervise([str(Path(d)/"missing.exe")],p,run_id="missing",log_dir=Path(d)/"logs",version="test")
            self.assertEqual(read_json(p)["state"],"failed")
            p.write_text("incomplete {")
            self.assertEqual(health(p)["state"],"unavailable")

    def test_status_readers_never_observe_partial_json_during_updates(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"runtime.json";atomic_json(p,{"iteration":-1})
            stop=threading.Event();failures=[]
            def reader():
                while not stop.is_set():
                    try:
                        json.loads(p.read_text())
                        time.sleep(.001)  # Readers release Windows file sharing between samples.
                    except PermissionError: time.sleep(.001)
                    except Exception as e: failures.append(type(e).__name__);break
            worker=threading.Thread(target=reader);worker.start()
            try:
                for i in range(40):atomic_json(p,{"iteration":i,"data":"x"*2048})
            finally:stop.set();worker.join()
            self.assertEqual(failures,[])


class LifetimeTests(unittest.TestCase):
    def test_background_allocations_cannot_trigger_automatic_tk_collection(self):
        enabled=gc.isenabled();guard=TkLifetime();seen=[]
        try:
            worker=threading.Thread(target=lambda:seen.append(gc.isenabled()))
            worker.start();worker.join()
            self.assertEqual(seen,[False])
            root=Mock();guard.attach(root)
            guard.collect()
            self.assertGreaterEqual(root.after.call_count,2)
        finally:guard.stop()
        self.assertEqual(gc.isenabled(),enabled)
