"""Display motion is independent of data refresh and UIA availability."""
from overlay_geometry import Rect


class Motion:
    def __init__(self, duration=0.18):
        self.duration = duration
        self.start = self.target = None
        self.start_alpha = self.target_alpha = 0
        self.at = 0

    def sample(self, now):
        if self.target is None:
            return None, 0, True
        t = min(1, max(0, (now-self.at)/self.duration)) if self.duration else 1
        eased = 1-(1-t)**3
        left = round(self.start.left+(self.target.left-self.start.left)*eased)
        top = round(self.start.top+(self.target.top-self.start.top)*eased)
        width=round(self.start.width+(self.target.width-self.start.width)*eased)
        height=round(self.start.height+(self.target.height-self.start.height)*eased)
        rect = Rect(left,top,left+max(1,width),top+max(1,height))
        return rect, round(self.start_alpha+(self.target_alpha-self.start_alpha)*eased), t >= 1

    def retarget(self, rect, alpha, now, immediate=False):
        if rect == self.target and alpha == self.target_alpha and not immediate:
            return
        current, value, _ = self.sample(now)
        self.start = current or rect
        self.start_alpha = value
        self.target, self.target_alpha, self.at = rect, alpha, now
        if immediate:
            self.start, self.start_alpha = rect, alpha
            self.at = now-self.duration
