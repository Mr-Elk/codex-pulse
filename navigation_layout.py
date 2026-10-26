"""A bounded presentation hold while a verified chat restores its side panel.

This never supplies composer geometry or a statistics identity. During a hold,
the previous shell stays in place and displays a neutral transition reading.
"""
from overlay_geometry import Rect,resize_from_left


class NavigationLayout:
    def __init__(self,timeout=3.0):
        self.timeout=timeout;self.host=self.title=self.window=self.composer=None
        self.until=0.;self.held=None;self.pending=False;self.waiting=False;self.missing=False;self.latest_at=-1.

    def clear(self):
        self.host=self.title=self.window=self.composer=None
        self.pending=False;self.waiting=False;self.missing=False;self.held=None;self.until=0.

    def holding(self,now):
        if self.held is not None and now>=self.until:
            self.pending=False
            if self.missing:self.waiting=True
            else:self.held=None;self.waiting=False
        return self.pending

    def showing(self,now):
        self.holding(now)
        return self.pending or self.waiting

    @staticmethod
    def same_anchor(a,b,tolerance=2):
        # Bottom controls differ by model/streaming state; the strip depends
        # only on the input's left/top/right, not its bottom edge.
        return isinstance(a,Rect) and isinstance(b,Rect) and all(abs(getattr(a,k)-getattr(b,k))<=tolerance for k in ('left','top','right'))

    def observe(self,host,title,composer,window,at,shown_rect,eligible):
        if at<self.latest_at:return
        self.latest_at=at
        if self.host!=host:
            self.clear();self.host=host
        if eligible is False:
            self.clear();return
        self.missing=composer is None
        # A missing observation cannot extend the transition deadline.
        if not title or eligible is None:
            self.holding(at);return
        changed=self.title is not None and title!=self.title
        moved=self.window is not None and window is not None and window!=self.window
        if moved:self.pending=False;self.waiting=False;self.held=None
        if changed and not moved and self.composer is not None and isinstance(shown_rect,Rect):
            if not self.pending:self.held=shown_rect
            self.pending=True;self.waiting=False;self.until=at+self.timeout
        self.title=title
        self.holding(at)
        if self.waiting and composer is not None:
            self.waiting=False;self.held=None
        if self.held is not None and at<self.until:
            # Matching the previous settled layout means the side panel has
            # returned. A temporarily wider composer never becomes a target.
            if self.same_anchor(composer,self.composer):
                self.pending=False
            else:self.pending=True;return
        if composer is not None and window is not None:
            self.composer,self.window=composer,window

    def presentation(self,window,height,now):
        if not self.showing(now):return None
        # Real window movement/resizing takes precedence over navigation hold.
        if self.window is not None and window!=self.window:
            self.pending=False;self.waiting=False;self.held=None;return None
        return resize_from_left(self.held,self.held.width,height) if self.held else None
