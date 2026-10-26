"""Shared rounded surfaces for our own native settings panel."""
import base64
import theme
import tkinter as tk
import tkinter.font as tkfont
import ui_tokens as ui

from font_policy import widget_family as family
from svg_art import paint, render_asset

BG, INK, MUTED = "#ffffff", "#233955", "#607088"
ACCENT, TINT, LINE = "#7865d6", "#f3f1fa", "#eeedf5"


def photo(master, png):
    return tk.PhotoImage(master=master, data=base64.b64encode(png))


class Surface(tk.Frame):
    def __init__(self, parent, scale, fill="#faf9fd", padx=14, pady=14, border=True):
        super().__init__(parent, bg=theme.color(BG), bd=0, highlightthickness=0)
        self.scale, self.fill = scale, fill
        self.clip_radius = 12
        self.clip_border = border
        self.clip_signature = None
        self.paint_signature=None
        self.asset="panel-card.svg" if border else "segment-track.svg"
        self.back = tk.Label(self, bg=theme.color(BG), bd=0, padx=0, pady=0)
        self.back.place(x=0, y=0, relwidth=1, relheight=1)
        self.inner = tk.Frame(self, bg=theme.color(fill), bd=0)
        self.inner.pack(fill="both", expand=True, padx=round(padx*scale), pady=round(pady*scale))
        self.bind("<Configure>", self.draw)
        self.inner.bind("<Configure>", self.clip_inner, add="+")

    def clip_inner(self, event=None):
        """Let the composited surface keep its border and rounded corners."""
        import os
        if os.name != 'nt': return
        x,y=self.inner.winfo_x(),self.inner.winfo_y()
        width,height=self.winfo_width(),self.winfo_height()
        signature=(x,y,width,height,self.clip_radius,self.clip_border)
        if self.clip_signature==signature or width<2 or height<2:return
        self.clip_signature=signature
        import ctypes as c
        from ctypes import wintypes as w
        gdi,user=c.WinDLL('gdi32'),c.WinDLL('user32')
        gdi.CreateRoundRectRgn.argtypes=[c.c_int]*6;gdi.CreateRoundRectRgn.restype=w.HRGN
        user.SetWindowRgn.argtypes=[w.HWND,w.HRGN,w.BOOL];user.SetWindowRgn.restype=c.c_int
        gdi.DeleteObject.argtypes=[w.HGDIOBJ]
        inset=round(self.scale) if self.clip_border else 0
        radius=round(self.clip_radius*self.scale)*2
        region=gdi.CreateRoundRectRgn(inset-x,inset-y,width-inset-x+1,height-inset-y+1,radius,radius)
        if region and not user.SetWindowRgn(self.inner.winfo_id(),region,True):gdi.DeleteObject(region)

    def draw(self, event):
        if event.width < 2 or event.height < 2:
            return
        signature=(event.width,event.height,self.fill,theme.current())
        if signature==self.paint_signature:return
        self.paint_signature=signature
        self.art = photo(self, render_asset(self.asset, event.width, event.height, self.scale, self.fill, BG))
        self.back.configure(image=self.art)


class Checkbox(tk.Canvas):
    """One themed check control with a panel-local Tcl variable."""
    def __init__(self,parent,variable,command,scale):
        self.variable,self.command,self.scale=variable,command,scale
        super().__init__(parent,width=round(18*scale),height=round(20*scale),bg=theme.color(BG),bd=0,highlightthickness=0,takefocus=True,cursor='hand2')
        self.trace=variable.trace_add('write',lambda *_:self.redraw())
        self.bind('<Button-1>',lambda _:self.invoke());self.bind('<space>',lambda _:self.invoke());self.bind('<Return>',lambda _:self.invoke())
        self.bind('<FocusIn>',lambda _:self.redraw());self.bind('<FocusOut>',lambda _:self.redraw());self.bind('<Destroy>',self.dispose)
        self.redraw()
    def invoke(self):
        self.variable.set(not self.variable.get());self.command();return 'break'
    def redraw(self):
        from strip_renderer import Renderer
        from svg_art import paint
        selected=bool(self.variable.get());r=Renderer(round(18*self.scale),self.scale,height=round(20*self.scale))
        try:
            r.rounded(1,2,15,15,3,theme.current() if selected else BG,theme.current() if selected or self.focus_get()==self else '#bdc9db')
            if selected:paint(r,'check.svg',2,3,13,13,{'currentColor':'#ffffff'})
            self.art=photo(self,r.png())
        finally:r.close()
        if not hasattr(self,'image_item'):self.image_item=self.create_image(0,0,anchor='nw',image=self.art)
        else:self.itemconfigure(self.image_item,image=self.art)
    def dispose(self,event):
        if event.widget==self:self.variable.trace_remove('write',self.trace)


class Segmented(tk.Frame):
    """One composited track; text buttons never paint cell-sized rectangles."""
    def __init__(self, parent, choices, command, scale, width=None, height=42, font_size=14):
        super().__init__(parent, bg=theme.color(BG), height=round(height*scale), width=round((width or 1)*scale))
        self.scale, self.command, self.choices = scale, command, list(choices)
        self.selected, self.buttons, self.signature = None, {}, None
        self.outer_radius=ui.SEGMENT_RADIUS if height<=34 else 12
        self.inner_radius=ui.SEGMENT_SELECTED_RADIUS if height<=34 else 9
        self.inset=3 if height<=34 else 4
        self.pointer_focus=False;self.pointer_key=None
        self.text_font = tkfont.Font(root=self, family=family(), size=-round(font_size*scale), weight="bold")
        self.pack_propagate(False)
        self.track = tk.Label(self, bg=theme.color(BG), bd=0, padx=0, pady=0)
        self.track.place(x=0, y=0, relwidth=1, relheight=1)
        self.track.bind("<Button-1>", self.press)
        for index, (key, title) in enumerate(self.choices):
            button = tk.Label(self, text=title,
                font=self.text_font, bg=theme.color(TINT), fg=theme.color("#59617b"),
                activebackground=theme.color(TINT), activeforeground=theme.color("#6f51cc"), relief="flat",
                bd=0, highlightthickness=0, padx=0, pady=0, cursor="hand2", takefocus=True)
            button.bind("<Left>", lambda _, index=index:self.step(index, -1))
            button.bind("<Right>", lambda _, index=index:self.step(index, 1))
            button.bind("<Return>", lambda _, key=key:self.activate(key))
            button.bind("<FocusIn>",self.draw);button.bind("<FocusOut>",self.focus_left)
            button.bind("<ButtonPress-1>",self.pointer_pressed)
            button.bind("<ButtonRelease-1>",lambda event,key=key:self.pointer_released(event,key))
            button.segment_key=key;button.invoke=lambda key=key:self.activate(key)
            self.buttons[key] = button
        self.bind("<Configure>", self.draw)

    def activate(self, key):
        self.select(key)
        self.command(key)
        return "break"

    def step(self, index, delta):
        self.pointer_focus=False
        key = self.choices[(index+delta) % len(self.choices)][0]
        self.buttons[key].focus_set()
        return self.activate(key)

    def press(self, event):
        index = min(len(self.choices)-1, max(0, int(event.x*len(self.choices)/max(1,self.winfo_width()))))
        self.pointer_focus=True;self.buttons[self.choices[index][0]].focus_set()
        self.activate(self.choices[index][0])

    def pointer_pressed(self,event):
        self.pointer_focus=True;self.pointer_key=event.widget.segment_key;event.widget.focus_set();self.draw()

    def pointer_released(self,event,key):
        pressed=self.pointer_key;self.pointer_key=None
        if pressed==key and 0<=event.x<event.widget.winfo_width() and 0<=event.y<event.widget.winfo_height():self.activate(key)
        return 'break'

    def focus_left(self,event=None):
        def settled():
            if not self.winfo_exists():return
            if self.focus_get() not in self.buttons.values():self.pointer_focus=False
            self.draw()
        self.after_idle(settled)

    def select(self, key):
        if key==self.selected:return
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
                             activebackground=theme.color(BG if selected else TINT),takefocus=selected)
            text_width = self.text_font.measure(title)+round(6*self.scale)
            text_height = min(height-round(8*self.scale), self.text_font.metrics("linespace")+round(4*self.scale))
            button.place(x=round(width*(index+.5)/len(self.choices)), y=height//2, anchor="center",
                         width=text_width, height=text_height)
        focused=not self.pointer_focus and self.focus_get() in self.buttons.values()
        signature = width, height, self.selected,theme.current(),focused
        if signature == self.signature:
            return
        from strip_renderer import Renderer
        renderer = Renderer(width, self.scale, height=height)
        try:
            w, h = width/self.scale, height/self.scale
            renderer.rounded(0,0,w,h,self.outer_radius,TINT)
            for index, (key, _) in enumerate(self.choices):
                if key == self.selected:
                    inset=self.inset
                    renderer.rounded(index*w/len(self.choices)+inset,inset,w/len(self.choices)-2*inset,h-2*inset,self.inner_radius,BG,
                                     theme.current() if focused else None)
            self.art = photo(self, renderer.png())
        finally:
            renderer.close()
        self.track.configure(image=self.art)
        self.signature = signature


class ModeCard(tk.Canvas):
    def __init__(self, parent, mode, title, description, command, scale):
        super().__init__(parent, bg=theme.color(BG), bd=0, height=round(72*scale), width=1,
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
        if self.selected==selected:return
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
        fill = "#f7f3fe" if self.selected else "#fbfcfe"
        border = theme.current() if self.selected or focus else "#d8e2f0"
        renderer = Renderer(width, s, height=height)
        try:
            paint(renderer, "panel-card.svg", 0, 0, w, h, {"currentColor":fill,"#e7e5ef":border})
            paint(renderer, "mode-"+self.mode+".svg", w-43, 13, 28, 14)
            renderer.ellipse(13, 29, 12, 12, "#8a72e8" if self.selected else "#c7c6d5", True)
            renderer.ellipse(16, 32, 6, 6, BG, True)
            self.art = photo(self, renderer.png())
        finally:
            renderer.close()
        self.delete("all")
        self.create_image(0, 0, anchor="nw", image=self.art)
        self.create_text(round(34*s),round(25*s),text=self.title,anchor="w",fill=theme.color(INK),
                         font=(family(),-round(14*s),"bold"),tags="mode-title")
        self.create_text(round(34*s),round(49*s),text=self.description,anchor="w",fill=theme.color(MUTED),
                         font=(family(),-round(12*s)),tags="mode-description")
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
        self.entry.bind('<FocusIn>',lambda _:self.draw());self.entry.bind('<FocusOut>',lambda _:self.draw())
        self.placeholder = tk.Label(self.entry,text="搜索工作会话",bg=theme.color(self.fill),fg=theme.color("#969aad"),
                                    font=(family(),-round(13*scale)),bd=0,padx=0,pady=0)
        self.placeholder.bind("<Button-1>",lambda _:self.entry.focus_set())
        self.trace = variable.trace_add("write",self.update_hint)
        self.bind("<Destroy>",self.dispose)
        self.update_hint()

    def draw(self,event=None):
        if not hasattr(self,'entry'):return
        width,height=self.winfo_width(),self.winfo_height()
        if width<2 or height<2:return
        from strip_renderer import Renderer
        r=Renderer(width,self.scale,height=height)
        try:
            r.rounded(.5,.5,width/self.scale-1,height/self.scale-1,12,self.fill,
                theme.current() if self.entry.focus_get()==self.entry else LINE)
            self.art=photo(self,r.png());self.back.configure(image=self.art)
        finally:r.close()
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
        self.create_text(width/2,height/2,text=self.title,font=self.font,fill=theme.color(ACCENT if enabled else "#69788d"))
        if enabled and self.focus_get()==self:
            self.create_line(12*self.scale,height-5*self.scale,width-12*self.scale,height-5*self.scale,fill=theme.color(ACCENT))
