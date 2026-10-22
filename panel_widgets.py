"""Shared rounded surfaces for our own native settings panel."""
import base64
import theme
import tkinter as tk
import tkinter.font as tkfont

from font_policy import family
from svg_art import paint, render_asset

BG, INK, MUTED = "#ffffff", "#1e2238", "#6f7691"
ACCENT, TINT, LINE = "#7865d6", "#f3f1fa", "#eeedf5"


def photo(master, png):
    return tk.PhotoImage(master=master, data=base64.b64encode(png))


class Surface(tk.Frame):
    def __init__(self, parent, scale, fill="#faf9fd", padx=14, pady=14, border=True):
        super().__init__(parent, bg=theme.color(BG), bd=0, highlightthickness=0)
        self.scale, self.fill = scale, fill
        self.asset="panel-card.svg" if border else "segment-track.svg"
        self.back = tk.Label(self, bg=theme.color(BG), bd=0, padx=0, pady=0)
        self.back.place(x=0, y=0, relwidth=1, relheight=1)
        self.inner = tk.Frame(self, bg=theme.color(fill), bd=0)
        self.inner.pack(fill="both", expand=True, padx=round(padx*scale), pady=round(pady*scale))
        self.bind("<Configure>", self.draw)

    def draw(self, event):
        if event.width < 2 or event.height < 2:
            return
        self.art = photo(self, render_asset(self.asset, event.width, event.height, self.scale, self.fill, BG))
        self.back.configure(image=self.art)


class Segmented(tk.Frame):
    """One composited track; text buttons never paint cell-sized rectangles."""
    def __init__(self, parent, choices, command, scale, width=None, height=42, font_size=14):
        super().__init__(parent, bg=theme.color(BG), height=round(height*scale), width=round((width or 1)*scale))
        self.scale, self.command, self.choices = scale, command, list(choices)
        self.selected, self.buttons, self.signature = None, {}, None
        self.text_font = tkfont.Font(root=self, family=family(), size=-round(font_size*scale), weight="bold")
        self.pack_propagate(False)
        self.track = tk.Label(self, bg=theme.color(BG), bd=0, padx=0, pady=0)
        self.track.place(x=0, y=0, relwidth=1, relheight=1)
        self.track.bind("<Button-1>", self.press)
        for index, (key, title) in enumerate(self.choices):
            button = tk.Button(self, text=title, command=lambda key=key:self.activate(key),
                font=self.text_font, bg=theme.color(TINT), fg=theme.color("#59617b"),
                activebackground=theme.color(TINT), activeforeground=theme.color("#6f51cc"), relief="flat", overrelief="flat",
                bd=0, highlightthickness=0, padx=0, pady=0, cursor="hand2", takefocus=True)
            button.bind("<Left>", lambda _, index=index:self.step(index, -1))
            button.bind("<Right>", lambda _, index=index:self.step(index, 1))
            button.bind("<Return>", lambda _, key=key:self.activate(key))
            self.buttons[key] = button
        self.bind("<Configure>", self.draw)

    def activate(self, key):
        self.select(key)
        self.command(key)
        return "break"

    def step(self, index, delta):
        key = self.choices[(index+delta) % len(self.choices)][0]
        self.buttons[key].focus_set()
        return self.activate(key)

    def press(self, event):
        index = min(len(self.choices)-1, max(0, int(event.x*len(self.choices)/max(1,self.winfo_width()))))
        self.activate(self.choices[index][0])

    def select(self, key):
        self.selected = key
        self.draw()

    def draw(self, event=None):
        width, height = self.winfo_width(), self.winfo_height()
        if width < 2 or height < 2:
            return
        for index, (key, title) in enumerate(self.choices):
            selected = key == self.selected
            button = self.buttons[key]
            button.configure(bg=theme.color(BG if selected else TINT), fg=theme.color("#6f51cc" if selected else "#59617b"),
                             activebackground=theme.color(BG if selected else TINT))
            text_width = self.text_font.measure(title)+round(6*self.scale)
            text_height = min(height-round(8*self.scale), self.text_font.metrics("linespace")+round(4*self.scale))
            button.place(x=round(width*(index+.5)/len(self.choices)), y=height//2, anchor="center",
                         width=text_width, height=text_height)
        signature = width, height, self.selected
        if signature == self.signature:
            return
        from strip_renderer import Renderer
        renderer = Renderer(width, self.scale, height=height)
        try:
            w, h = width/self.scale, height/self.scale
            paint(renderer, "segment-track.svg", 0, 0, w, h, {"currentColor":TINT})
            for index, (key, _) in enumerate(self.choices):
                if key == self.selected:
                    paint(renderer, "segment-track.svg", index*w/len(self.choices)+4, 4,
                          w/len(self.choices)-8, h-8, {"currentColor":BG})
            self.art = photo(self, renderer.png())
        finally:
            renderer.close()
        self.track.configure(image=self.art)
        self.signature = signature


class ModeCard(tk.Canvas):
    def __init__(self, parent, mode, title, description, command, scale):
        super().__init__(parent, bg=theme.color(BG), bd=0, height=round(150*scale), width=1,
                         highlightthickness=0, takefocus=True, cursor="hand2")
        self.mode, self.title, self.description = mode, title, description
        self.command, self.scale, self.selected = command, scale, False
        self.signature = None
        self.bind("<Configure>", self.draw)
        self.bind("<Button-1>", lambda _:self.invoke())
        self.bind("<space>", lambda _:self.invoke())
        self.bind("<Return>", lambda _:self.invoke())
        self.bind("<FocusIn>", self.draw)
        self.bind("<FocusOut>", self.draw)

    def invoke(self):
        self.command()
        return "break"

    def select(self, selected):
        self.selected = selected
        self.draw()

    def draw(self, event=None):
        width, height = self.winfo_width(), self.winfo_height()
        if width < 2:
            return
        focus = self.focus_get() == self
        signature = width, height, self.selected, focus
        if signature == self.signature:
            return
        from strip_renderer import Renderer
        s = self.scale
        w, h = width/s, height/s
        fill = "#f7f4ff" if self.selected else "#fcfbff"
        border = "#9581df" if self.selected or focus else "#e7e5ef"
        renderer = Renderer(width, s, height=height)
        try:
            paint(renderer, "panel-card.svg", 0, 0, w, h, {"currentColor":fill,"#e7e5ef":border})
            paint(renderer, "mode-"+self.mode+".svg", (w-128)/2, 13, 128, 60)
            renderer.ellipse(w-27, 12, 14, 14, "#8a72e8" if self.selected else "#c7c6d5", True)
            renderer.ellipse(w-23.5, 15.5, 7, 7, BG, True)
            self.art = photo(self, renderer.png())
        finally:
            renderer.close()
        self.delete("all")
        self.create_image(0, 0, anchor="nw", image=self.art)
        self.create_text(width/2,round(99*s),text=self.title,anchor="center",fill=theme.color(INK),
                         font=(family(),-round(14*s),"bold"),tags="mode-title")
        self.create_text(width/2,round(126*s),text=self.description,anchor="center",fill=theme.color(MUTED),
                         font=(family(),-round(11*s)),tags="mode-description")
        self.signature = signature


class SearchField(Surface):
    def __init__(self, parent, variable, scale):
        super().__init__(parent, scale, "#f8f8fc", padx=12, pady=7)
        self.configure(height=round(40*scale))
        self.pack_propagate(False)
        self.variable = variable
        self.icon = photo(self, render_asset("search.svg",round(18*scale),round(18*scale),scale))
        tk.Label(self.inner,image=self.icon,bg=theme.color(self.fill),bd=0).pack(side="left",padx=(0,round(8*scale)))
        self.entry = tk.Entry(self.inner,textvariable=variable,font=(family(),-round(13*scale)),
                              bg=theme.color(self.fill),fg=theme.color(INK),insertbackground=theme.color(ACCENT),relief="flat",bd=0,
                              highlightthickness=0)
        self.entry.pack(side="left",fill="both",expand=True)
        self.placeholder = tk.Label(self.entry,text="搜索工作会话",bg=theme.color(self.fill),fg=theme.color("#969aad"),
                                    font=(family(),-round(13*scale)),bd=0,padx=0,pady=0)
        self.placeholder.bind("<Button-1>",lambda _:self.entry.focus_set())
        self.trace = variable.trace_add("write",self.update_hint)
        self.bind("<Destroy>",self.dispose)
        self.update_hint()

    def update_hint(self, *_):
        if self.variable.get():
            self.placeholder.place_forget()
        else:
            self.placeholder.place(x=1,rely=.5,anchor="w")

    def dispose(self, event):
        if event.widget == self:
            self.variable.trace_remove("write",self.trace)


class ActionButton(tk.Canvas):
    """A clean inactive action, without Windows disabled-bitmap stippling."""
    def __init__(self,parent,text,command,scale):
        self.title,self.command,self.scale=text,command,scale
        self.control_state="normal"
        font=(family(),-round(13*scale))
        width=tkfont.Font(master=parent,font=font).measure(text)+round(26*scale)
        super().__init__(parent,bg=theme.color(BG),bd=0,highlightthickness=0,width=width,
                         height=round(38*scale),takefocus=True,cursor="hand2")
        self.font=font
        self.bind("<Configure>",lambda _:self.draw())
        self.bind("<Button-1>",lambda _:self.invoke())
        self.bind("<space>",lambda _:self.invoke())
        self.bind("<Return>",lambda _:self.invoke())
        self.bind("<FocusIn>",lambda _:self.draw())
        self.bind("<FocusOut>",lambda _:self.draw())

    def cget(self,key):
        return self.control_state if key=="state" else super().cget(key)

    __getitem__=cget

    def configure(self,cnf=None,**kwargs):
        if "text" in kwargs:
            self.title=kwargs.pop("text")
            kwargs["width"]=tkfont.Font(master=self,font=self.font).measure(self.title)+round(26*self.scale)
        if "state" in kwargs:
            self.control_state=str(kwargs.pop("state"))
            enabled=self.control_state=="normal"
            kwargs.update(takefocus=enabled,cursor="hand2" if enabled else "arrow")
        result=super().configure(cnf,**kwargs)
        if hasattr(self,"font"):self.draw()
        return result

    def invoke(self):
        if self.control_state=="normal":self.command()
        return "break"

    def draw(self):
        width,height=self.winfo_width(),self.winfo_height()
        if width<2:return
        enabled=self.control_state=="normal"
        self.art=photo(self,render_asset("segment-track.svg",width,height,self.scale,
                                       "#eee8fb" if enabled else "#f5f4f8",BG))
        self.delete("all")
        self.create_image(0,0,anchor="nw",image=self.art)
        self.create_text(width/2,height/2,text=self.title,font=self.font,fill=theme.color(ACCENT if enabled else "#aaa5ba"))
        if enabled and self.focus_get()==self:
            self.create_line(12*self.scale,height-5*self.scale,width-12*self.scale,height-5*self.scale,fill=theme.color(ACCENT))
