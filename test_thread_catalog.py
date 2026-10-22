from pathlib import Path
import sqlite3
import json
import tempfile
import unittest

from thread_catalog import CatalogCache, recent


class CatalogTests(unittest.TestCase):
    def test_work_choices_use_types_and_filter_before_limit(self):
        with tempfile.TemporaryDirectory() as folder:
            home = Path(folder)
            identity = lambda n: f"00000000-0000-0000-0000-{n:012d}"
            with sqlite3.connect(home/"state_5.sqlite") as db:
                db.execute("CREATE TABLE threads(id TEXT,title TEXT,archived INTEGER,updated_at INTEGER,source TEXT,thread_source TEXT)")
                db.executemany("INSERT INTO threads VALUES(?,?,?,?,?,?)", [
                    (identity(1),"工作中的聊天模块",0,1,"vscode","user"),
                    (identity(2),"自动创建的工作任务",0,2,"vscode","agent_created_thread"),
                    (identity(3),"工作",1,30,"vscode","user"),
                    (identity(4),"工作",0,40,"chatgpt","user"),
                    (identity(5),"工作",0,50,'{"subagent":{"other":"guardian"}}',"guardian_review"),
                    (identity(6),"工作",0,60,"vscode","subagent"),
                    (identity(7),"工作",0,70,"vscode","guardian_review"),
                    (identity(8),"工作",0,80,"unknown","user"),
                ])
            db.close()
            before = (home/"state_5.sqlite").read_bytes()
            self.assertEqual([i["id"] for i in recent(home,limit=None,work_only=True)], [identity(2),identity(1)])
            self.assertEqual(recent(home,limit=1,work_only=True)[0]["id"], identity(2))
            self.assertEqual((home/"state_5.sqlite").read_bytes(), before)

    def test_work_cache_observes_archive_and_unarchive(self):
        with tempfile.TemporaryDirectory() as folder:
            home = Path(folder)
            identity = "00000000-0000-0000-0000-000000000001"
            with sqlite3.connect(home/"state_5.sqlite") as db:
                db.execute("CREATE TABLE threads(id TEXT,title TEXT,archived INTEGER,updated_at INTEGER,source TEXT,thread_source TEXT)")
                db.execute("INSERT INTO threads VALUES(?,?,0,1,'vscode','user')", (identity,"测试工作"))
            db.close()
            cache = CatalogCache(work_only=True, include_archived=False)
            self.assertEqual(len(cache.read(home)), 1)
            with sqlite3.connect(home/"state_5.sqlite") as db:
                db.execute("UPDATE threads SET archived=1")
            db.close()
            self.assertEqual(cache.read(home), [])
            with sqlite3.connect(home/"state_5.sqlite") as db:
                db.execute("UPDATE threads SET archived=0")
            db.close()
            self.assertEqual(cache.read(home)[0]["id"], identity)

    def test_legacy_work_source_without_thread_source_is_supported(self):
        with tempfile.TemporaryDirectory() as folder:
            home = Path(folder)
            identity = "00000000-0000-0000-0000-000000000001"
            with sqlite3.connect(home/"state_5.sqlite") as db:
                db.execute("CREATE TABLE threads(id TEXT,title TEXT,archived INTEGER,updated_at INTEGER,source TEXT)")
                db.execute("INSERT INTO threads VALUES(?,?,0,1,'vscode')", (identity,"旧工作记录"))
            db.close()
            self.assertEqual(recent(home,work_only=True), [{"id":identity,"title":"旧工作记录"}])

    def test_unknown_schema_does_not_guess_work_type(self):
        with tempfile.TemporaryDirectory() as folder:
            home = Path(folder)
            with sqlite3.connect(home/"state_5.sqlite") as db:
                db.execute("CREATE TABLE threads(id TEXT,title TEXT,archived INTEGER,updated_at INTEGER)")
                db.execute("INSERT INTO threads VALUES('00000000-0000-0000-0000-000000000001','工作',0,1)")
            db.close()
            self.assertEqual(recent(home,work_only=True), [])

    def test_explicit_choices_exclude_archived_and_malformed_ids(self):
        with tempfile.TemporaryDirectory() as folder:
            home=Path(folder)
            path=home/"state_5.sqlite"
            identity="01a124b5-5ca6-7402-8dcb-9d85f94e7677"
            with sqlite3.connect(path) as db:
                db.execute("CREATE TABLE threads(id TEXT,title TEXT,archived INTEGER,updated_at INTEGER)")
                db.executemany("INSERT INTO threads VALUES(?,?,?,?)",[(identity,"明确选择",0,1),
                                ("invalid","无效记录",0,3),(identity,"归档",1,4)])
            db.close()
            before=path.read_bytes()
            self.assertEqual(recent(home),[{"id":identity,"title":"明确选择"}])
            self.assertEqual(path.read_bytes(),before)
            (home/"session_index.jsonl").write_text(json.dumps({"id":identity,"thread_name":"真实显示名称"}),encoding="utf-8")
            self.assertEqual(recent(home),[{"id":identity,"title":"真实显示名称"}])

    def test_auto_catalog_has_no_recency_cutoff_and_includes_archived(self):
        with tempfile.TemporaryDirectory() as folder:
            home=Path(folder)
            with sqlite3.connect(home/"state_5.sqlite") as db:
                db.execute("CREATE TABLE threads(id TEXT,title TEXT,archived INTEGER,updated_at INTEGER)")
                db.executemany("INSERT INTO threads VALUES(?,?,?,?)",[(f"00000000-0000-0000-0000-{i:012d}",f"标题{i}",int(i==1),i) for i in range(1,30)])
            db.close()
            self.assertEqual(len(recent(home)),20)
            self.assertEqual(len(recent(home,limit=None,include_archived=True)),29)
