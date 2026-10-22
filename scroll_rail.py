"""Transient, antialiased scroll thumbs in a stable gutter outside the content."""
import base64
import tkinter as tk

import theme


class SlimScrollbar(tk.Canvas):
    HIDE_DELAY = 1000
    FADE_STEPS = 10

    def __init__(self, parent, command, scale):
        super().__init__(parent, width=round(12*scale), bg="#ffffff", bd=0,
                         highlightthickness=0, takefocus=False)
        self.command, self.scale = command, scale
        self.first, self.last = 0., 1.
        self.overflow = self.hovered = self.dragging = self.disposed = False
        self.opacity = 0.
        self.hide_job = self.fade_job = None
        self.top = self.thumb = self.anchor = 0
        self.bind("<Configure>", self.redraw)
        self.bind("<Enter>", self.enter)
        self.bind("<Leave>", self.leave)
        self.bind("<Button-1>", self.press)
        self.bind("<B1-Motion>", self.drag)
        self.bind("<ButtonRelease-1>", self.release)
        self.bind("<MouseWheel>", self.wheel)
        self.bind("<FocusIn>", self.reveal)
        self.bind("<FocusOut>", self.leave)
        for key, args in (("Up", ("scroll", -1, "units")), ("Down", ("scroll", 1, "units")),
                          ("Prior", ("scroll", -1, "pages")), ("Next", ("scroll", 1, "pages")),
                          ("Home", ("moveto", 0)), ("End", ("moveto", 1))):
            self.bind("<"+key+">", lambda _, args=args: self.move(*args))
        self.bind("<Destroy>", self.dispose)

    def cancel(self, name):
        job = getattr(self, name)
        if job:
            self.after_cancel(job)
            setattr(self, name, None)

    def set(self, first, last):
        first, last = max(0., float(first)), min(1., float(last))
        moved = abs(first-self.first) > .00001
        self.first, self.last = first, max(first, last)
        self.overflow = self.last-self.first < .999
        self.configure(takefocus=self.overflow)
        if not self.overflow:
            self.cancel("hide_job"); self.cancel("fade_job")
            self.opacity = 0.
        elif moved or self.hovered or self.dragging:
            self.reveal()
        self.redraw()

    def reveal(self, event=None):
        if self.disposed or not self.overflow:
            return
        self.cancel("hide_job"); self.cancel("fade_job")
        self.opacity = 1.
        self.redraw()
        if not self.hovered and not self.dragging and self.focus_get() != self:
            self.hide_job = self.after(self.HIDE_DELAY, self.fade)

    def fade(self, step=1):
        self.hide_job = self.fade_job = None
        if self.disposed or self.hovered or self.dragging or self.focus_get() == self:
            return
        self.opacity = max(0., 1-step/self.FADE_STEPS)
        self.redraw()
        if step < self.FADE_STEPS:
            self.fade_job = self.after(18, lambda: self.fade(step+1))

    def enter(self, event=None):
        self.hovered = True
        self.reveal()

    def leave(self, event=None):
        self.hovered = False
        self.reveal()

    @property
    def ink_role(self):
        return "#7865d6" if self.hovered or self.dragging else "#b9add6"

    @property
    def ink(self):
        return theme.color(self.ink_role)

    def redraw(self, event=None):
        if self.disposed:
            return
        self.delete("all")
        height, width = max(1, self.winfo_height()), max(2, self.winfo_width())
        pad = min(3*self.scale, height/4)
        track = max(1, height-2*pad)
        visible = min(1., max(0., self.last-self.first))
        self.thumb = min(track, max(32*self.scale, visible*track))
        fraction = min(1., self.first/max(.00001, 1-visible))
        self.top = pad+fraction*(track-self.thumb)
        self.travel = track-self.thumb
        self.ink_width = (6 if self.hovered or self.dragging else 4)*self.scale
        if not self.overflow or self.opacity <= 0:
            return
        from strip_renderer import Renderer
        length = max(2, round(self.thumb))
        renderer = Renderer(width, self.scale, height=length)
        try:
            ink = "#"+f"{round(255*self.opacity):02x}"+self.ink_role[1:]
            w = min(width, self.ink_width)/self.scale
            renderer.rounded((width/self.scale-w)/2, 0, w, length/self.scale,
                             min(w/2, length/self.scale/2), ink)
            self.thumb_png = renderer.png()
            self.art = tk.PhotoImage(master=self, data=base64.b64encode(self.thumb_png))
        finally:
            renderer.close()
        self.create_image(0, self.top, anchor="nw", image=self.art)

    def move(self, *args):
        if self.overflow:
            self.command(*args)
            self.reveal()
        return "break"

    def wheel(self, event):
        return self.move("scroll", -1 if event.delta > 0 else 1, "units")

    def press(self, event):
        if not self.overflow:
            return "break"
        self.dragging = True
        self.anchor = event.y-self.top if self.top <= event.y <= self.top+self.thumb else self.thumb/2
        self.reveal()
        return self.drag(event)

    def drag(self, event):
        if self.dragging:
            pad = min(3*self.scale, self.winfo_height()/4)
            fraction = max(0., min(1., (event.y-self.anchor-pad)/max(1., self.travel)))
            return self.move("moveto", fraction*max(0., 1-(self.last-self.first)))
        return "break"

    def release(self, event=None):
        self.dragging = False
        self.reveal()
        return "break"

    def dispose(self, event=None):
        if event is not None and event.widget != self:
            return
        self.cancel("hide_job"); self.cancel("fade_job")
        self.disposed = True
