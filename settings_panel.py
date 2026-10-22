"""Native quick settings: live preview, direct controls and a separate session tab."""
import base64
from pathlib import Path
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk

import overlay_style as style
import thread_catalog
import theme
from svg_art import render_asset
from font_policy import family
from scroll_rail import SlimScrollbar
from panel_widgets import Segmented, Surface, ModeCard, SearchField, ActionButton

BG, INK, MUTED = "#ffffff", "#1e2238", "#6f7691"
ACCENT, TINT, LINE = "#7865d6", "#f3f1fa", "#eeedf5"
METRICS = {
    "speed": ("TPS", "最近完成请求的平均估算"),
    "tokens": ("Token", "输入与输出累计，含重复上下文"),
    "cache": ("缓存命中率", "最近请求的已缓存输入占比"),
    "context": ("上下文估算", "最近请求的上下文占用估算"),
    "rounds": ("轮次和请求", "当前会话累计任务轮次与请求数"),
}


class VectorButton(tk.Button):
    """Native button text and keyboard behavior over a scalable SVG surface."""
    def __init__(self, parent, text, command, scale, quiet=False, color=ACCENT, surface_bg=BG, height=38, font_size=13):
        self.scale, self.fill = scale, BG if quiet else TINT
        self.text_color, self.quiet = color, quiet
        font = (family(), -round(font_size*scale))
        measured = tkfont.Font(master=parent, font=font).measure(text)
        self.draw_width, self.draw_height = measured+round(24*scale), round(height*scale)
        super().__init__(parent, text=text, command=command, relief="flat", bd=0,
                         bg=theme.color(surface_bg), fg=theme.color(color), activebackground=theme.color(surface_bg), activeforeground=theme.color(ACCENT),
                         disabledforeground=theme.color("#aaa5ba"),
                         cursor="hand2", takefocus=True, font=font, compound="center",
                         highlightthickness=0, padx=0, pady=0)
        self.bind("<Configure>", self.resize)
        self.redraw()

    def redraw(self):
        if self.cget("state")=="disabled":
            # Windows stipples a disabled button bitmap. Keep a transparent
            # sizing image so its inactive text stays clean and readable.
            self.art=tk.PhotoImage(master=self,width=max(2,self.draw_width),height=self.draw_height)
        else:
            png = render_asset("control.svg", max(2,self.draw_width), self.draw_height, self.scale, self.fill,self.cget("background"))
            self.art = tk.PhotoImage(master=self, data=base64.b64encode(png))
        super().configure(image=self.art)

    def resize(self, event):
        if event.width > 1 and event.width != self.draw_width:
            self.draw_width = event.width
            self.redraw()

    def configure(self, cnf=None, **kwargs):
        if cnf is not None:
            return super().configure(cnf, **kwargs)
        repaint = False
        if "state" in kwargs and kwargs["state"]!=self.cget("state"):
            repaint=True
        if "bg" in kwargs:
            fill = kwargs.pop("bg")
            repaint = self.fill != fill
            self.fill = fill
        if "text" in kwargs and kwargs["text"] != self.cget("text"):
            font = tkfont.Font(master=self, font=self.cget("font"))
            self.draw_width = font.measure(kwargs["text"])+round(24*self.scale)
            repaint = True
        result = super().configure(**kwargs)
        if repaint:
            self.redraw()
        return result


class ThemeButton(tk.Canvas):
    """A fixed seed swatch with themed selection and keyboard activation."""
    def __init__(self, parent, name, seed, command, scale, surface_bg):
        super().__init__(parent, width=round(88*scale), height=round(36*scale),
                         bg=theme.color(surface_bg), bd=0, highlightthickness=0,
                         takefocus=True, cursor="hand2")
        self.name,self.seed,self.command,self.scale=name,seed,command,scale
        self.selected=False
        self.bind("<Configure>",lambda _:self.redraw())
        self.bind("<FocusIn>",lambda _:self.redraw())
        self.bind("<FocusOut>",lambda _:self.redraw())
        self.bind("<Button-1>",lambda _:self.invoke())
        self.bind("<space>",lambda _:self.invoke())
        self.bind("<Return>",lambda _:self.invoke())

    def invoke(self):
        self.command()
        return "break"

    def select(self, selected):
        if self.selected != selected:
            self.selected=selected
            self.redraw()

    def redraw(self):
        width,height=self.winfo_width(),round(36*self.scale)
        if width<2:return
        from strip_renderer import Renderer
        from svg_art import paint
        renderer=Renderer(width,self.scale,height=height)
        try:
            fill=TINT if self.selected else BG
            border=ACCENT if self.selected or self.focus_get()==self else LINE
            paint(renderer,"panel-card.svg",0,0,width/self.scale,height/self.scale,
                  {"currentColor":fill,"#e7e5ef":border})
            # The dot must share the supersampled image, not a second aliased
            # Tk oval. Its literal seed must not pass through theme mapping.
            from strip_renderer import call
            brush=renderer.new("GdipCreateSolidFill","GdipDeleteBrush",int("ff"+self.seed[1:],16))
            call("GdipFillEllipse",renderer.g,brush,10,13,10,10)
            self.png=renderer.png()
            self.art=tk.PhotoImage(master=self,data=base64.b64encode(self.png))
        finally:
            renderer.close()
        self.delete("all")
        self.create_image(0,0,anchor="nw",image=self.art)
        self.create_text(round(27*self.scale),height/2,anchor="w",text=self.name,
                         fill=theme.color(ACCENT if self.selected else "#59617b"),
                         font=(family(),-round(13*self.scale),"bold" if self.selected else "normal"))


class CloseButton(VectorButton):
    def __init__(self, parent, command, scale):
        super().__init__(parent, "×", command, scale, quiet=True, color=MUTED, height=36)
        self.configure(font=(family(), -round(23*scale)))
        self.draw_width=round(36*scale)
        self.tip=None;self.tip_job=None
        self.redraw()
        self.bind("<Enter>", self.enter)
        self.bind("<Leave>", self.leave)
        self.bind("<Destroy>", self.leave)

    def enter(self, _):
        self.configure(bg=theme.color(TINT), fg=theme.color(ACCENT))
        self.tip_job=self.after(550,self.show_tip)

    def show_tip(self):
        self.tip_job=None
        self.tip=tk.Toplevel(self)
        self.tip.overrideredirect(True)
        self.tip.geometry(f"+{self.winfo_rootx()}+{self.winfo_rooty()+self.winfo_height()+4}")
        tk.Label(self.tip,text="关闭",font=(family(),-round(12*self.scale)),
                 bg=theme.color(INK),fg=theme.color(BG),padx=8,pady=4).pack()

    def leave(self, event=None):
        if self.tip_job:self.after_cancel(self.tip_job);self.tip_job=None
        if self.tip:self.tip.destroy();self.tip=None
        if event is None or event.type != tk.EventType.Destroy:self.configure(bg=theme.color(BG),fg=theme.color(MUTED))


class Toggle(tk.Canvas):
    """A keyboard-operable native toggle bound to the existing preference variable."""
    def __init__(self, parent, variable, command, scale):
        self.variable, self.command, self.scale = variable, command, scale
        self.width, self.height = round(44*scale), round(26*scale)
        super().__init__(parent, width=self.width, height=self.height, bg=theme.color(BG),
                         bd=0, highlightthickness=1, highlightbackground=theme.color(BG),
                         highlightcolor=theme.color(ACCENT), takefocus=True, cursor="hand2")
        self.trace = variable.trace_add("write", lambda *_: self.draw())
        self.bind("<Button-1>", self.toggle)
        self.bind("<space>", self.toggle)
        self.bind("<Return>", self.toggle)
        self.bind("<Destroy>", self.dispose)
        self.draw()

    def draw(self):
        enabled = bool(self.variable.get())
        png = render_asset("toggle-on.svg" if enabled else "toggle-off.svg", self.width,self.height,self.scale)
        self.art = tk.PhotoImage(master=self, data=base64.b64encode(png))
        if not hasattr(self, "item"):
            self.item = self.create_image(1,1,anchor="nw",image=self.art)
        else:
            self.itemconfigure(self.item,image=self.art)

    def toggle(self, _=None):
        self.variable.set(not self.variable.get())
        self.command()
        return "break"

    def dispose(self, _):
        self.variable.trace_remove("write", self.trace)


class SettingsPanel:
    def __init__(self, owner, x, y, tab="strip"):
        self.owner = owner
        self.scale = owner.scale
        self.closed = False
        owner.animation_choice = tk.BooleanVar(master=owner.root,value=owner.animations)
        self.tab = "strip"
        self.preview_key = None
        self.focus_check = None
        self.catalog_job = None
        # A separate Tcl/Tk root avoids Toplevel creation/focus mutating the
        # withdrawn Tk root that hosts our externally painted layered HWND.
        self.window = tk.Tk()
        self.window.report_callback_exception = owner.root.report_callback_exception
        self.window.withdraw()
        self.window.overrideredirect(True)
        self.window.configure(bg=theme.color(LINE))
        self.window.title("Codex Pulse 设置")
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.window.bind("<Escape>", lambda _: self.close())
        self.shell = tk.Frame(self.window, bg=theme.color(BG))
        self.shell.pack(fill="both", expand=True, padx=1, pady=1)
        self.header = tk.Frame(self.shell, bg=theme.color(BG))
        self.header.pack(fill="x", padx=self.px(20), pady=(self.px(14), self.px(10)))
        self.logo = tk.PhotoImage(master=self.window, data=base64.b64encode(
            render_asset("brand.svg",self.px(36),self.px(36),self.scale)))
        self.logo_label=tk.Label(self.header, image=self.logo, bg=theme.color(BG))
        self.logo_label.pack(side="left", padx=(0, self.px(10)))
        self.label(self.header, "Codex Pulse", 20, bold=True).pack(side="left")
        self.close_button=CloseButton(self.header,self.close,self.scale)
        self.close_button.pack(side="right")
        self.tabs = Segmented(self.shell,(("strip","统计条"),("display","显示"),("session","会话")),self.show_tab,self.scale,font_size=15)
        self.tabs.pack(fill="x", padx=self.px(16))
        self.tab_buttons = self.tabs.buttons
        self.rule(self.shell, pad=16)
        footer = tk.Frame(self.shell, bg=theme.color(BG))
        footer.pack(side="bottom", fill="x", padx=self.px(16), pady=(0, self.px(12)))
        self.button(footer, "恢复默认位置", self.reset_position, quiet=True, font_size=14).pack(side="left")
        self.button(footer, "统计口径", lambda: self.show_tab("help"), quiet=True, font_size=14).pack(side="left")
        self.button(footer, "关闭统计条", owner.close, quiet=True, color=MUTED, font_size=14).pack(side="right")
        content_host = tk.Frame(self.shell, bg=theme.color(BG))
        content_host.pack(fill="both", expand=True, padx=(self.px(20),self.px(32)), pady=self.px(8))
        self.content = tk.Canvas(content_host, bg=theme.color(BG), bd=0, highlightthickness=0, height=1)
        self.content.pack(side="left", fill="both", expand=True)
        # Rails live in the shell margin, never inside the content canvas/cards.
        # Their hit areas are permanent; appearing thumbs cannot resize content.
        self.scroller = SlimScrollbar(self.shell, self.content.yview,self.scale)
        self.scroller.place(in_=self.content,relx=1,x=self.px(12),y=0,width=self.px(12),relheight=1)
        self.content.configure(yscrollcommand=self.outer_scroll_set)
        self.body = tk.Frame(self.content, bg=theme.color(BG))
        self.body_item = self.content.create_window(0, 0, anchor="nw", window=self.body)
        self.body.bind("<Configure>", lambda _: self.update_scroll())
        self.content.bind("<Configure>", self.resize_content)
        self.window.bind("<MouseWheel>", self.scroll)
        self.show_tab(tab if tab in ("strip","display","session") else "strip")
        self.refresh()
        self.window.update_idletasks()
        self.content.configure(height=self.body.winfo_reqheight())
        self.window.update_idletasks()
        width, height = self.px(480), self.px(780)
        area = owner.win.work_area(owner.target["hwnd"]) if owner.target else None
        if area is None:
            from overlay_geometry import Rect
            area = Rect(0, 0, self.window.winfo_screenwidth(), self.window.winfo_screenheight())
        margin = min(self.px(12), max(0, (area.height-self.px(320))//2))
        width, height = min(width, area.width), min(height, area.height-2*margin)
        left = max(area.left, min(x-width+self.px(24), area.right-width))
        top = max(area.top+margin, min(y-height-self.px(10), area.bottom-margin-height))
        self.window.geometry(f"{width}x{height}{left:+d}{top:+d}")
        self.window.update_idletasks()
        self.hwnd = owner.win.top_level(self.window.winfo_id())
        from panel_chrome import Chrome
        self.chrome = Chrome(self.hwnd)
        owner.win.own_overlay(self.hwnd,owner.target["hwnd"] if owner.display_mode=="composer" and owner.target else None)
        if owner.display_mode=="desktop":
            owner.win.set_floating(self.hwnd,True)
        self.window.deiconify()
        self.window.lift()
        self.window.focus_force()  # User explicitly opened settings; draft focus is untouched otherwise.
        self.window.bind("<FocusOut>", self.focus_out)

    def px(self, value):
        return round(value*self.scale)

    def label(self, parent, text, size=14, color=INK, bold=False, bg=BG, **kwargs):
        return tk.Label(parent, text=text, bg=theme.color(bg), fg=theme.color(color), anchor=kwargs.pop("anchor","w"),
                        bd=0, padx=0, pady=0, highlightthickness=0,
                        font=(family(), -self.px(size), "bold" if bold else "normal"), **kwargs)

    def button(self, parent, text, command, quiet=False, color=ACCENT, font_size=13):
        return VectorButton(parent,text,command,self.scale,quiet,color,font_size=font_size)

    def rule(self, parent, pad=0):
        tk.Frame(parent, bg=theme.color(LINE), height=1).pack(fill="x", padx=self.px(pad), pady=self.px(5))

    def resize_content(self, event):
        self.content.itemconfigure(self.body_item, width=event.width)
        self.update_scroll()
        self.refresh()

    def update_scroll(self):
        if self.tab == "session" and hasattr(self,"choices") and self.choices.winfo_exists():
            # Give the list the remaining viewport instead of growing the whole
            # page. Its own scrollbar handles large catalogs; controls stay put.
            viewport = self.content.winfo_height()
            if viewport > self.px(100):
                other = self.body.winfo_reqheight()-self.choices.winfo_reqheight()
                preferred = getattr(self,"session_list_preferred",self.px(190))
                height = max(self.px(96),min(preferred,viewport-other-self.px(2)))
                if self.choices.winfo_reqheight() != height:
                    self.choices.configure(height=height)
                    return  # The resulting Configure event settles scroll bounds.
        self.content.configure(scrollregion=self.content.bbox("all"))
        if self.body.winfo_reqheight() <= self.content.winfo_height()+2:
            self.content.yview_moveto(0)
        self.position_session_rail()

    def outer_scroll_set(self, first, last):
        self.scroller.set(first,last)
        self.position_session_rail()

    def position_session_rail(self):
        if self.tab != "session" or not hasattr(self,"session_scroll"):
            return
        # The independent rail is clipped to the visible list portion when the
        # short-screen fallback scrolls the whole page. It never covers footer.
        top=max(0,self.tree.winfo_rooty()-self.content.winfo_rooty())
        bottom=min(self.content.winfo_height(),self.tree.winfo_rooty()+self.tree.winfo_height()-self.content.winfo_rooty())
        if bottom-top < self.px(24):
            self.session_scroll.place_forget()
        else:
            self.session_scroll.place(in_=self.content,relx=1,x=0,y=top,width=self.px(12),height=bottom-top)

    def scroll(self, event):
        if self.tab == "session" and str(event.widget).startswith(str(self.tree)):
            return
        if self.body.winfo_reqheight() > self.content.winfo_height():
            self.content.yview_scroll(-1 if event.delta > 0 else 1, "units")
            return "break"

    def show_tab(self, tab):
        if self.catalog_job:
            self.window.after_cancel(self.catalog_job)
            self.catalog_job = None
        if hasattr(self,"session_scroll"):
            self.session_scroll.destroy()
            del self.session_scroll
        self.tab = tab
        self.content.yview_moveto(0)
        for widget in self.body.winfo_children():
            widget.destroy()
        self.tabs.select(tab)
        if tab == "strip":
            self.build_strip()
        elif tab == "display":
            self.build_display()
        elif tab == "session":
            self.build_session()
        else:
            self.build_help()
        self.apply_theme(theme.current())

    def switch(self, parent, variable, command):
        return Toggle(parent, variable, command, self.scale)

    def build_strip(self):
        self.preview_caption = self.label(self.body, "预览 · 当前会话", 12, MUTED)
        self.preview_caption.pack(fill="x", pady=(0, self.px(5)))
        self.preview = tk.Canvas(self.body, bg=theme.color(BG), width=1,height=self.px(64),bd=0,highlightthickness=0)
        self.preview.pack(fill="x", pady=(0, self.px(9)))
        self.preview_item=self.preview.create_image(0,0,anchor="nw")
        self.preview_key = None
        self.label(self.body, "显示指标", 12, MUTED).pack(fill="x", pady=(0, self.px(4)))
        self.metric_toggles = {}
        for key, (title, description) in METRICS.items():
            row = tk.Frame(self.body, bg=theme.color(BG))
            row.pack(fill="x", pady=self.px(7))
            words = tk.Frame(row, bg=theme.color(BG))
            words.pack(side="left", fill="x", expand=True)
            self.label(words, title, 15, bold=True).pack(fill="x")
            self.label(words, description, 13, MUTED).pack(fill="x",pady=(self.px(3),0))
            toggle = self.switch(row, self.owner.metric_choices[key], self.change_metrics)
            toggle.pack(side="right")
            self.metric_toggles[key] = toggle
        self.rule(self.body)
        font_row = tk.Frame(self.body, bg=theme.color(BG))
        font_row.pack(fill="x", pady=self.px(3))
        self.label(font_row, "文字大小").pack(side="left")
        self.font_segments=Segmented(font_row,((13,"紧凑"),(15,"标准"),(17,"大字")),self.change_font,self.scale,width=214,height=40)
        self.font_segments.pack(side="right")
        self.font_buttons=self.font_segments.buttons
        mouse_row = tk.Frame(self.body, bg=theme.color(BG))
        mouse_row.pack(fill="x", pady=self.px(7))
        words = tk.Frame(mouse_row, bg=theme.color(BG))
        words.pack(side="left")
        self.label(words, "鼠标穿透").pack(fill="x")
        self.label(words, "两侧按钮始终可操作", 12, MUTED).pack(fill="x",pady=(self.px(3),0))
        self.switch(mouse_row, self.owner.lock_choice, self.owner.toggle_lock).pack(side="right")
        self.feedback = self.label(self.body, "", 10, MUTED)
        self.feedback.pack(fill="x")
        self.refresh()

    def build_display(self):
        self.label(self.body,"显示方式",17,bold=True).pack(fill="x",pady=(self.px(4),self.px(6)))
        self.label(self.body,"选择统计条出现的位置",12,MUTED).pack(fill="x")
        modes = tk.Frame(self.body,bg=theme.color(BG))
        modes.pack(fill="x",pady=(self.px(17),self.px(14)))
        self.mode_buttons = {}
        for index,(mode,title,description) in enumerate((("composer","输入框上方","随聊天窗口移动"),
                                                       ("desktop","桌面胶囊","跨应用保留显示"))):
            button = ModeCard(modes,mode,title,description,lambda mode=mode:self.change_mode(mode),self.scale)
            button.grid(row=0,column=index,sticky="nsew",padx=(0,self.px(12)) if index==0 else 0)
            modes.grid_columnconfigure(index,weight=1,uniform="mode")
            self.mode_buttons[mode] = button
        hint=Surface(self.body,self.scale,fill=theme.color("#f8f7fc"),padx=14,pady=12,border=False)
        hint.pack(fill="x",pady=(0,self.px(15)))
        self.mode_hint=self.label(hint.inner,"",12,MUTED,bg=theme.color(hint.fill),wraplength=self.px(390),justify="left")
        self.mode_hint.pack(fill="x")
        colors=Surface(self.body,self.scale,fill=theme.color("#faf9fd"),padx=14,pady=12)
        colors.pack(fill="x",pady=(0,self.px(14)))
        self.label(colors.inner,"主题颜色",14,bold=True,bg=theme.color(colors.fill)).pack(fill="x")
        self.label(colors.inner,"主色生成浅色背景与清晰文字，应用到统计条和面板",12,MUTED,bg=theme.color(colors.fill),
                   wraplength=self.px(370),justify="left").pack(fill="x",pady=(self.px(4),self.px(8)))
        presets=tk.Frame(colors.inner,bg=theme.color(colors.fill));presets.pack(fill="x")
        self.theme_buttons={}
        for index,(name,value) in enumerate(theme.PRESETS):
            button=ThemeButton(presets,name,value,lambda value=value:self.owner.set_theme_color(value),
                               self.scale,surface_bg=colors.fill)
            button.grid(row=index//4,column=index%4,sticky="ew",
                        padx=(0,self.px(6)) if index%4<3 else 0,pady=(0,self.px(6)))
            self.theme_buttons[value]=button
        for column in range(4):
            presets.grid_columnconfigure(column,weight=1,uniform="theme")
        from color_editor import ColorEditor
        self.color_editor=ColorEditor(colors.inner,self.scale,theme.current(),self.owner.set_theme_color,
                                      lambda parent,text,command,quiet=False:VectorButton(
                                          parent,text,command,self.scale,quiet=quiet,surface_bg=colors.fill,height=34),
                                      fill=colors.fill)
        self.color_editor.pack(fill="x",pady=(self.px(6),0))
        self.theme_value=self.color_editor.status
        motion_row = tk.Frame(self.body,bg=theme.color(BG))
        motion_row.pack(fill="x",pady=self.px(8))
        words=tk.Frame(motion_row,bg=theme.color(BG));words.pack(side="left")
        self.label(words,"平滑移动",14,bold=True).pack(fill="x")
        self.label(words,"拖动与位置变化时平滑过渡",12,MUTED).pack(fill="x",pady=(self.px(4),0))
        self.switch(motion_row,self.owner.animation_choice,self.owner.toggle_animations).pack(side="right")
        self.compact_row=tk.Frame(self.body,bg=theme.color(BG))
        words=tk.Frame(self.compact_row,bg=theme.color(BG));words.pack(side="left")
        self.label(words,"收起为胶囊",14,bold=True).pack(fill="x")
        self.label(words,"点击胶囊可展开统计",12,MUTED).pack(fill="x",pady=(self.px(4),0))
        self.compact_choice=tk.BooleanVar(master=self.window,value=self.owner.compact)
        self.compact_button=self.switch(self.compact_row,self.compact_choice,self.change_compact)
        self.compact_button.pack(side="right")
        self.refresh()

    def choose_theme_color(self):
        self.color_editor.toggle_picker()

    def apply_theme(self, previous):
        theme.repaint(self,previous)
        self.logo=tk.PhotoImage(master=self.window,data=base64.b64encode(
            render_asset("brand.svg",self.px(36),self.px(36),self.scale)))
        self.logo_label.configure(image=self.logo)
        self.preview_key=None
        self.refresh()

    def change_metrics(self):
        self.owner.select_metrics()
        selected = sum(bool(choice.get()) for choice in self.owner.metric_choices.values())
        self.feedback.configure(text="至少保留一项指标" if selected == 1 else "设置已保存")
        self.refresh()

    def change_font(self, size):
        self.owner.set_font_size(size)
        self.refresh()

    def change_mode(self, mode):
        self.owner.set_display_mode(mode)
        self.refresh()

    def change_compact(self):
        self.owner.toggle_compact()
        self.refresh()

    def reset_position(self):
        self.owner.reset_position()
        if self.tab == "strip":
            self.feedback.configure(text="已恢复输入框上方自动定位")

    def build_session(self):
        current=Surface(self.body,self.scale)
        current.pack(fill="x",pady=(self.px(4),self.px(15)))
        self.label(current.inner,"统计方式",11,MUTED,bg=theme.color(current.fill)).pack(fill="x",pady=(0,self.px(8)))
        self.binding_modes=Segmented(current.inner,(("auto","自动跟随"),("fixed","固定会话")),
                                     self.change_binding_mode,self.scale,height=40)
        self.binding_modes.pack(fill="x",pady=(0,self.px(12)))
        caption=tk.Frame(current.inner,bg=theme.color(current.fill));caption.pack(fill="x",pady=(0,self.px(8)))
        self.label(caption,"当前统计会话",11,MUTED,bg=theme.color(current.fill)).pack(side="left")
        badge=Surface(caption,self.scale,fill=theme.color("#eee8fa"),padx=8,pady=3,border=False)
        badge.pack(side="right")
        self.binding_status=self.label(badge.inner,"",11,ACCENT,bg=theme.color(badge.fill))
        self.binding_status.pack()
        self.session_title=self.label(current.inner,"",14,bold=True,bg=theme.color(current.fill),
                                      wraplength=self.px(390),justify="left")
        self.session_title.pack(fill="x")
        self.binding_description=self.label(current.inner,"",12,MUTED,bg=theme.color(current.fill),
                                             wraplength=self.px(390),justify="left")
        self.binding_description.pack(fill="x",pady=(self.px(4),0))
        self.label(self.body,"仅显示未归档的工作会话",12,MUTED).pack(fill="x",pady=(self.px(11),self.px(7)))
        self.search = tk.StringVar(master=self.window)
        self.search_field=SearchField(self.body,self.search,self.scale)
        self.search_field.pack(fill="x")
        heading=tk.Frame(self.body,bg=theme.color(BG));heading.pack(fill="x",pady=(self.px(16),self.px(7)))
        self.label(heading,"工作会话",12,MUTED).pack(side="left")
        self.result_count=self.label(heading,"",12,MUTED);self.result_count.pack(side="right")
        self.choices=Surface(self.body,self.scale,fill=theme.color(BG),padx=6,pady=6)
        self.choices.configure(height=self.px(190))
        self.choices.pack(fill="x")
        self.choices.pack_propagate(False)
        tree_theme=ttk.Style(self.window)
        self.tree_style="Pulse.Treeview"
        tree_theme.layout(self.tree_style,[("Treeview.treearea",{"sticky":"nswe"})])
        tree_theme.configure(self.tree_style,font=(family(),-self.px(13)),rowheight=self.px(42),
                        background=theme.color(BG),fieldbackground=theme.color(BG),foreground=theme.color(INK),borderwidth=0,indent=0)
        tree_theme.map(self.tree_style,background=theme.color([("selected",TINT)]),foreground=theme.color([("selected",ACCENT)]))
        self.configure_session_tree()
        self.tree=ttk.Treeview(self.choices.inner,columns=("current",),show="tree",selectmode="browse",style=self.tree_style)
        self.tree.column("#0",width=self.px(300),minwidth=self.px(80),stretch=True)
        self.tree.column("current",width=self.px(48),minwidth=self.px(48),anchor="e",stretch=False)
        self.tree.pack(side="left",fill="both",expand=True)
        self.listbox=self.tree
        self.session_scroll=SlimScrollbar(self.shell,self.tree.yview,self.scale)
        self.tree.configure(yscrollcommand=self.session_scroll_set)
        self.tree_icon=tk.PhotoImage(master=self.window,data=base64.b64encode(render_asset("rounds.svg",self.px(18),self.px(18),self.scale)))
        self.empty_state=self.label(self.choices.inner,"没有可选的工作会话\n试试其他关键词或解除归档",12,MUTED,justify="center",anchor="center")
        self.session_catalog = thread_catalog.CatalogCache(work_only=True, include_archived=False)
        self.catalog = self.session_catalog.read(self.owner.args.codex_home.resolve())
        self.search.trace_add("write", lambda *_: self.filter_sessions())
        self.tree.bind("<<TreeviewSelect>>",lambda _:self.selection_state())
        self.tree.bind("<Double-Button-1>", lambda _: self.choose_session())
        self.tree.bind("<Return>", lambda _: self.choose_session())
        actions=tk.Frame(self.body,bg=theme.color(BG));actions.pack(fill="x",pady=(self.px(12),0))
        self.selection_hint=self.label(actions,"选择后可固定统计对象",11,MUTED)
        self.selection_hint.pack(side="left")
        self.choose_button = ActionButton(actions, "固定所选会话", self.choose_session,self.scale)
        self.choose_button.pack(side="right")
        self.filter_sessions()
        self.refresh()
        self.catalog_job = self.window.after(1000, self.refresh_session_catalog)

    def configure_session_tree(self):
        tree_theme=ttk.Style(self.window)
        tree_theme.configure(self.tree_style,background=theme.color(BG),fieldbackground=theme.color(BG),foreground=theme.color(INK))
        tree_theme.map(self.tree_style,background=theme.color([("selected",TINT)]),foreground=theme.color([("selected",ACCENT)]))

    def refresh_session_catalog(self):
        self.catalog_job = None
        if self.closed or self.tab != "session":
            return
        items = self.session_catalog.read(self.owner.args.codex_home.resolve())
        if items != self.catalog:
            selected = self.selected_session_id()
            self.catalog = items
            self.filter_sessions(selected)
        self.catalog_job = self.window.after(1000, self.refresh_session_catalog)

    def session_scroll_set(self,first,last):
        self.session_scroll.set(first,last)
        self.position_session_rail()

    def filter_sessions(self, selected_id=None):
        term = self.search.get().casefold().strip()
        self.matches = [i for i in self.catalog if term in i["title"].casefold()]
        self.tree.delete(*self.tree.get_children())
        for index,item in enumerate(self.matches):
            self.tree.insert("","end",iid=str(index),text="  "+item["title"],image=self.tree_icon,
                             values=("当前" if item["id"]==self.owner.binding.identity else "",))
            if item["id"] == selected_id:
                self.tree.selection_set(str(index))
        self.result_count.configure(text=f"{len(self.matches)} 项")
        self.session_list_preferred=self.px(min(348,max(96,len(self.matches)*42+12)))
        self.update_scroll()
        self.empty_state.place_forget()
        if not self.matches:
            self.empty_state.place(relx=.5,rely=.5,anchor="center")
        self.selection_state()

    def selection_state(self):
        selected=self.selected_session_id()
        same=selected is not None and self.owner.binding.mode=="fixed" and selected==self.owner.binding.identity
        self.choose_button.configure(state="normal" if selected and not same else "disabled",
                                     text="已固定此会话" if same else "固定所选会话")
        self.selection_hint.configure(text="已固定，可继续选择其他会话" if same else
                                      "确认固定后停止自动跟随" if selected and self.owner.binding.mode=="auto" else
                                      "确认后切换统计对象" if selected else "选择后点击固定")

    def selected_session_id(self):
        selection = self.tree.selection()
        if selection and int(selection[0]) < len(self.matches):
            return self.matches[int(selection[0])]["id"]
        return None

    def choose_session(self):
        selected = self.selected_session_id()
        if selected is not None:
            # Recheck eligibility at click time: archiving may happen between
            # list refresh and selection. Never pin a stale or hidden item.
            self.catalog = thread_catalog.recent(self.owner.args.codex_home.resolve(), limit=None, work_only=True)
            item = next((item for item in self.catalog if item["id"] == selected), None)
            self.filter_sessions(selected)
            if item is None:
                return
            self.owner.select_thread(item["id"], item["title"])
            self.refresh()

    def change_follow(self):
        self.owner.toggle_follow()
        self.refresh()

    def change_binding_mode(self, mode):
        self.owner.follow_choice.set(mode=="auto")
        self.owner.toggle_follow()
        self.refresh()
        if mode=="fixed" and not self.owner.binding.identity:
            self.search_field.entry.focus_set()

    def build_help(self):
        self.label(self.body, "统计口径", 17, bold=True).pack(fill="x", pady=self.px(10))
        for title, text in (
            ("TPS 是平均估算", "输出 Token ÷ 请求耗时，包含网络和首 Token 等待。完成请求后更新，生成中不会显示旧速度。"),
            ("Token 是累计用量", "输入包含重复发送的上下文；推理 Token 已包含在输出中。"),
            ("上下文占用是估算", "来自最近请求的记录，不代表账户剩余额度。"),
            ("数据来自本机记录", "无法识别或缺少记录时显示不可用。同名会话请在会话页手动选择。")):
            self.label(self.body, title, 13, bold=True).pack(fill="x", pady=(self.px(12), self.px(4)))
            self.label(self.body, text, 12, MUTED, wraplength=self.px(370), justify="left").pack(fill="x")
        self.button(self.body, "返回统计条设置", lambda: self.show_tab("strip")).pack(anchor="w", pady=self.px(14))

    def refresh(self):
        if self.closed:
            return
        owner = self.owner
        if self.tab == "session":
            binding=owner.binding
            self.binding_modes.select(binding.mode)
            if binding.mode=="fixed":
                badge="已固定" if binding.identity else "待选择"
                title=owner.bound_title if binding.identity else "请选择要固定的工作会话"
                description="切换窗口时，仍统计这条工作会话。" if binding.identity else "在下方选择工作会话，再点击固定所选会话。"
            elif binding.identity:
                badge,title,description="已识别",owner.bound_title,"切换工作会话时，统计对象自动切换。"
            else:
                badge,title,description={
                    "ambiguous":("需选择","存在同名工作会话","请从下方选择并固定统计对象。"),
                    "not_found":("无记录","当前页面没有本地记录","切到有本地记录的工作会话，或从下方固定。"),
                    "unavailable":("暂不可用","暂时无法识别当前窗口","切回工作窗口后重试，也可以从下方固定。"),
                }.get(binding.status,("待识别","等待识别当前工作会话","切回工作窗口后自动识别，也可以从下方固定。"))
            self.session_title.configure(text=title)
            self.binding_status.configure(text=badge)
            self.binding_description.configure(text=description)
            for index,item in enumerate(self.matches):
                self.tree.item(str(index),values=("当前" if item["id"]==owner.binding.identity else "",))
            self.selection_state()
        if self.tab == "display":
            for mode,button in self.mode_buttons.items():
                button.select(mode==owner.display_mode)
            self.mode_hint.configure(text="可在桌面拖动；切换应用时仍保留。" if owner.display_mode=="desktop" else "跟随输入框位置；切换到其他应用时隐藏。")
            self.compact_choice.set(owner.compact)
            for value,button in self.theme_buttons.items():
                button.select(value==theme.current())
            name=next((name for name,value in theme.PRESETS if value==theme.current()),"自定义")
            self.color_editor.sync(theme.current(),name)
            if owner.display_mode=="desktop":
                self.compact_row.pack(fill="x",pady=self.px(13))
            else:
                self.compact_row.pack_forget()
            return
        if self.tab != "strip":
            return
        snapshot = {**(owner.snapshot or {}), "visible_metrics": owner.visible_metrics}
        width=max(1,self.content.winfo_width())
        key = (owner.font_size,width,theme.current(),tuple(style.metrics(snapshot).values()))
        if width>self.px(100) and key != self.preview_key:
            # Render at the actual selected size. A narrow preview uses the same
            # priority rules as the real strip instead of shrinking every glyph.
            png, _ = owner.render_strip(snapshot, width, self.scale*owner.font_size/15)
            self.preview_image = tk.PhotoImage(master=self.window, data=base64.b64encode(png).decode("ascii"))
            self.preview.configure(height=self.preview_image.height())
            self.preview.itemconfigure(self.preview_item,image=self.preview_image)
            self.preview_key = key
        note = "刷新中" if snapshot.get("from_cache") else "当前会话" if snapshot.get("available") else "暂无会话数据"
        self.preview_caption.configure(text="预览 · "+note)
        self.font_segments.select(owner.font_size)

    def focus_out(self, _):
        if not self.closed and not getattr(self,"modal_open",False):
            if self.focus_check:
                self.window.after_cancel(self.focus_check)
            self.focus_check = self.window.after(100, self.close_if_outside)

    def close_if_outside(self):
        self.focus_check = None
        if not self.closed and not getattr(self,"modal_open",False) and self.window.focus_displayof() is None:
            self.close()

    def close(self):
        if self.closed:
            return
        self.closed = True
        owner = self.owner
        if self.catalog_job:
            self.window.after_cancel(self.catalog_job)
            self.catalog_job = None
        if self.focus_check:
            self.window.after_cancel(self.focus_check)
            self.focus_check = None
        focused = getattr(self, "hwnd", None) == owner.win.user32.GetForegroundWindow()
        self.chrome.close()
        self.window.destroy()
        owner.settings_panel = None
        owner.menu_open = False
        # Restore only our panel's focus, never override a switch to another app.
        if focused and owner.target and not owner.stop.is_set():
            owner.win.user32.SetForegroundWindow(owner.target["hwnd"])
        owner.refresh_input_mode(bool(owner.target and owner.win.active_target(owner.target["hwnd"])))
        if not owner.stop.is_set():
            owner.root.after_idle(owner.refresh_surface)
