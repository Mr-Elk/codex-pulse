"""Bind only a uniquely matched main-document title, never the newest session."""
from dataclasses import dataclass, replace

from session_titles import clean_title


@dataclass(frozen=True)
class Binding:
    mode: str = "auto"
    identity: str | None = None
    title: str = "正在识别当前对话"
    status: str = "waiting"
    revision: int = 0

    def follow(self, title, catalog, probe_status="ok"):
        if self.mode != "auto":
            return self
        if probe_status != "ok" or not clean_title(title):
            identity, display, status = None, "当前对话暂不可识别", "unavailable"
        else:
            matches = {item["id"] for item in catalog if item["title"] == title}
            if len(matches) == 1:
                identity, display, status = matches.pop(), title, "matched_title"
            elif matches:
                identity, display, status = None, "同名对话 · 请右键选择", "ambiguous"
            else:
                identity, display, status = None, "当前页面暂无本地统计", "not_found"
        if (identity, display, status) == (self.identity, self.title, self.status):
            return self
        return replace(self, identity=identity, title=display, status=status, revision=self.revision+1)

    def pin(self, identity, title):
        return Binding("fixed", identity, title, "manual", self.revision+1)

    def manual(self):
        if self.identity:
            return self.pin(self.identity, self.title)
        return Binding("fixed", None, "请选择要固定的工作会话", "manual_pending", self.revision+1)

    def automatic(self):
        return Binding(revision=self.revision+1)

    def accepts(self, identity, revision):
        return self.identity is not None and self.identity == identity and self.revision == revision
