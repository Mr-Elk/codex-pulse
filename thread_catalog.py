"""Read local IDs/display titles; recency is never evidence of UI focus."""
import re
import sqlite3
import json
import time
from contextlib import closing
from session_titles import clean_title


def recent(home, limit=20, include_archived=False, *, work_only=False):
    path = home / "state_5.sqlite"
    try:
        with closing(sqlite3.connect(path.as_uri()+"?mode=ro",uri=True,timeout=0.15)) as db:
            db.execute("PRAGMA query_only=ON")
            query = "SELECT id,title FROM threads"
            conditions, params = [], []
            if not include_archived:
                conditions.append("archived=0")
            if work_only:
                columns = {row[1] for row in db.execute("PRAGMA table_info(threads)")}
                if "source" not in columns:
                    return []  # Unknown types cannot be offered as work choices.
                conditions.append("source IN (?,?,?,?)")
                params.extend(("vscode", "cli", "exec", "appServer"))
                if "thread_source" in columns:
                    conditions.append("(thread_source IS NULL OR thread_source IN ('user','agent_created_thread'))")
            if conditions:
                query += " WHERE " + " AND ".join(conditions)
            query += " ORDER BY updated_at DESC"
            if limit is not None:
                query += " LIMIT ?"
                params.append(limit)
            rows = db.execute(query, params).fetchall()
        rows = [(identity,title) for identity,title in rows
                if isinstance(identity,str) and re.fullmatch(r"[0-9a-fA-F-]{36}",identity)]
        wanted, names = {identity for identity,_ in rows}, {}
        try:
            with (home/"session_index.jsonl").open("rb") as index:
                for line in index:
                    try:
                        record=json.loads(line)
                        if not isinstance(record,dict):
                            continue
                        identity,name=record.get("id"),record.get("thread_name")
                        if isinstance(identity,str) and identity in wanted and clean_title(name):
                            names[identity]=name
                    except (ValueError,UnicodeDecodeError):
                        continue
        except OSError:
            pass
        # Some database titles are original prompts, not display names. Prefer
        # the session-index name and never put multiline prompts into the UI.
        return [{"id":identity,"title":names.get(identity) or (title if clean_title(title) else "对话 "+identity[:8])}
                for identity,title in rows]
    except (sqlite3.Error,OSError,ValueError):
        return []


class CatalogCache:
    def __init__(self, *, work_only=False, include_archived=True):
        self.work_only, self.include_archived = work_only, include_archived
        self.signature = None
        self.items = []
        self.refreshed_at = 0

    def read(self, home):
        signature = []
        for name in ("state_5.sqlite", "state_5.sqlite-wal", "session_index.jsonl"):
            try:
                stat = (home / name).stat()
                signature.append((stat.st_mtime_ns, stat.st_size))
            except OSError:
                signature.append(None)
        signature = tuple(signature)
        now = time.monotonic()
        refresh_after = 30 if self.items else 0.5
        if signature != self.signature or now - self.refreshed_at > refresh_after:
            self.items = recent(home, limit=None, include_archived=self.include_archived, work_only=self.work_only)
            self.signature, self.refreshed_at = signature, now
        return self.items
