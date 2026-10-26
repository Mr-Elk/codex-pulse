"""Bound composer geometry to a host/document, with one bounded uncertain interval."""
from dataclasses import dataclass


@dataclass
class ComposerContext:
    host: int | None = None
    title: str | None = None
    composer: object = None
    window: object = None
    latest_at: float = -1
    uncertain_since: float | None = None
    reason: str | None = "context_pending"
    generation: int = 0
    grace: float = 1.0

    def invalidate(self, reason):
        if self.composer is not None or self.reason != reason:
            self.generation += 1
        self.composer = self.window = None
        self.uncertain_since = None
        self.reason = reason

    def expire(self, now):
        if self.uncertain_since is not None and now - self.uncertain_since >= self.grace:
            self.invalidate(self.reason or "context_pending")
        return self.composer is not None

    def observe(self, host, composer, window, at, title, status, metadata=None):
        if at < self.latest_at:
            return "stale"
        self.latest_at = at
        metadata = metadata or {}
        if self.host != host:
            self.invalidate("context_pending")
            self.host, self.title = host, None
        reliable_title = status == "ok" and isinstance(title, str) and bool(title.strip())
        changed = reliable_title and self.title is not None and title != self.title
        if changed:
            self.invalidate("context_pending")
        if reliable_title:
            self.title = title
        if metadata.get("page_kind") == "non_work":
            self.invalidate("non_work_page")
            return "clear"
        if reliable_title and composer is not None and window is not None:
            self.composer, self.window = composer, window
            self.uncertain_since, self.reason = None, None
            return "bind"
        if (reliable_title and self.composer is not None and metadata.get("geometry_moved") is True
                and metadata.get("composer_status")=="found" and metadata.get("page_kind")=="work"):
            # The named input still exists on the same document; only absolute
            # geometry raced a moving host. anchored_bounds reprojects it.
            self.uncertain_since,self.reason = None,None
            return "bind"
        reason = "no_composer" if metadata.get("composer_status") == "absent" else "context_pending"
        if self.composer is not None:
            if self.uncertain_since is None:
                self.uncertain_since = at
                self.reason = reason
            if self.expire(at):
                return "hold"
        self.reason = reason
        return "bind" if changed else "clear"
