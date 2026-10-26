"""Compact v19 native controls, modal drafts and consistent dropdown behavior."""
import tkinter as tk
from tkinter import ttk
import theme
import ui_tokens as ui
from panel_widgets import Surface, photo
from svg_art import render_asset
from font_policy import widget_family as family

BG,INK,MUTED,ACCENT='#ffffff','#233955','#607088','#7865d6'

class MenuItem(Surface):
    def __init__(self,p,parent,title,selected,disabled,command):
        self.selected,self.disabled,self.command,self.keyboard_focus=selected,disabled,command,False
        super().__init__(parent,p.scale,fill='#f7f3fe' if selected else BG,padx=10,pady=0,border=False)
        self.clip_radius=6;self.configure(height=p.px(ui.MENU_ROW),takefocus=not disabled,cursor='' if disabled else 'hand2');self.pack_propagate(False)
        label=p.label(self.inner,title,ui.CONTROL_SIZE,'#69788d' if disabled else ACCENT if selected else INK,bg=self.fill);label.pack(side='left',fill='y');self.caption=label
        if selected:
            self.check=photo(self,render_asset('check.svg',p.px(14),p.px(14),p.scale,theme.current()))
            mark=tk.Label(self.inner,image=self.check,bg=theme.color(self.fill),bd=0);mark.pack(side='right')
        for widget in (self,self.back,self.inner,*self.inner.winfo_children()):widget.bind('<Button-1>',lambda _:self.invoke())
        self.bind('<Return>',lambda _:self.invoke());self.bind('<space>',lambda _:self.invoke())
        self.bind('<Enter>',lambda _:self.highlight(True));self.bind('<Leave>',lambda _:self.after_idle(lambda:self.highlight(False)))
        self.bind('<FocusIn>',lambda _:self.highlight(False));self.bind('<FocusOut>',lambda _:self.highlight(False))
    def highlight(self,hovered):
        if not self.winfo_exists() or self.disabled:return
        if not hovered:
            x,y=self.winfo_pointerxy();hovered=self.winfo_rootx()<=x<self.winfo_rootx()+self.winfo_width() and self.winfo_rooty()<=y<self.winfo_rooty()+self.winfo_height()
        self.fill='#f7f3fe' if self.selected or hovered or (self.keyboard_focus or self.focus_get()==self) else BG
        for child in (self.inner,*self.inner.winfo_children()):child.configure(bg=theme.color(self.fill))
        from types import SimpleNamespace
        self.draw(SimpleNamespace(width=self.winfo_width(),height=self.winfo_height()))
    def draw(self,event=None):
        if not hasattr(self,'disabled'):return
        width,height=self.winfo_width(),self.winfo_height()
        if width<2 or height<2:return
        from strip_renderer import Renderer
        r=Renderer(width,self.scale,height=height)
        try:
            r.rounded(.5,.5,width/self.scale-1,height/self.scale-1,6,self.fill,
                '#d8e2f0' if not self.disabled and (self.keyboard_focus or self.focus_get()==self) else None)
            self.art=photo(self,r.png());self.back.configure(image=self.art)
        finally:r.close()
    def invoke(self):
        if not self.disabled:self.command()
        return 'break'

class Select(Surface):
    def __init__(self,p,parent,choices,value,command,width=ui.FIELD_WIDTH):
        super().__init__(parent,p.scale,fill=BG,padx=13,pady=0)
        self.clip_radius=8
        self.p,self.choices,self.command=p,list(choices),command;self.value=None;self.popup=None;self.hovered=False;self.select_signature=None
        self.configure(width=p.px(width),height=p.px(ui.CONTROL_HEIGHT),takefocus=True,cursor='hand2');self.pack_propagate(False)
        self.label=p.label(self.inner,'',ui.CONTROL_SIZE,INK);self.label.pack(side='left',fill='x',expand=True)
        self.arrow=photo(self,render_asset('chevron-down.svg',p.px(14),p.px(14),p.scale))
        self.arrow_label=tk.Label(self.inner,image=self.arrow,bg=theme.color(BG),bd=0);self.arrow_label.pack(side='right')
        for widget in (self,self.back,self.inner,self.label,self.arrow_label):
            widget.bind('<Button-1>',lambda _:self.open());widget.bind('<Enter>',lambda _:self.hover(True));widget.bind('<Leave>',lambda _:self.hover(False))
        self.bind('<FocusIn>',lambda _:self.draw());self.bind('<FocusOut>',lambda _:self.draw())
        for sequence in ('<Return>','<space>','<Down>','<Up>','<Home>','<End>','<Escape>'):
            self.bind(sequence,lambda event,sequence=sequence:self.key(sequence,event))
        self.set(value)
    def key(self,sequence,event=None):
        if self.popup is not None:
            return self.menu_keys.get(sequence,lambda event:None)(event)
        if sequence in ('<Return>','<space>','<Down>'):
            self.open();return 'break'
    def set(self,value):
        self.value=value
        title=next((x[1] for x in self.choices if x[0]==value),'暂未提供')
        if self.label.cget('text')!=title:self.label.configure(text=title)
    def set_choices(self,choices):
        choices=list(choices)
        if self.choices!=choices:self.choices=choices;self.set(self.value)
    def hover(self,enabled):
        if self.hovered!=enabled:self.hovered=enabled;self.draw()
    def draw(self,event=None):
        if not hasattr(self,'popup'):return
        width,height=self.winfo_width(),self.winfo_height()
        if width<2 or height<2:return
        signature=(width,height,bool(self.popup),self.hovered,self.focus_get()==self,theme.current())
        if signature==self.select_signature:return
        self.select_signature=signature
        from strip_renderer import Renderer
        renderer=Renderer(width,self.p.scale,height=height)
        try:
            color=theme.current() if self.popup or self.focus_get()==self else '#a9bfdc' if self.hovered else '#d8e2f0'
            renderer.rounded(.6,.6,width/self.p.scale-1.2,height/self.p.scale-1.2,8,BG,color)
            self.art=photo(self,renderer.png());self.back.configure(image=self.art)
        finally:renderer.close()
    def open(self):
        if self.popup is not None:return
        was_modal=getattr(self.p,'modal_open',False);previous_grab=self.grab_current()
        p=self.p;p.modal_open=True;parent=self.winfo_toplevel();w=tk.Toplevel(parent);self.popup=w;w.withdraw();w.transient(parent);w.overrideredirect(True);w.configure(bg=theme.color(BG));w.attributes('-topmost',True)
        from panel_chrome import PopupCard
        w.pulse_card=PopupCard(w,p.scale,padx=4,pady=4);buttons=[];parent_keys={}
        def close():
            if self.popup is None:return
            self.popup=None;p.modal_open=was_modal;self.draw()
            for sequence,(old,token) in parent_keys.items():
                parent.unbind(sequence,token)
                if old:parent.bind(sequence,old)
            try:
                w.grab_release();w.pulse_card.close();w.destroy()
                if previous_grab is not None and previous_grab.winfo_exists():previous_grab.grab_set()
                self.focus_set()
            except tk.TclError:pass
        def choose(key):
            close();self.set(key);self.command(key)
        self.cancel=close
        for item in self.choices:
            key,title=item[:2];disabled=bool(item[2]) if len(item)>2 else False
            button=MenuItem(p,w.pulse_card.body,title,key==self.value,disabled,lambda key=key:choose(key));button.pack(fill='x')
            if not disabled:buttons.append(button)
        w.menu_items=buttons
        w.update_idletasks();area=p.owner.win.work_area(p.hwnd);width=max(self.winfo_width(),w.winfo_reqwidth());height=w.winfo_reqheight()
        left=max(area.left,min(self.winfo_rootx(),area.right-width));below=self.winfo_rooty()+self.winfo_height()+p.px(5)
        top=below if below+height<=area.bottom else max(area.top,self.winfo_rooty()-height-p.px(5))
        w.geometry(f'{width}x{min(height,area.height)}+{left}+{top}')
        def outside(event):
            if not (left<=event.x_root<left+width and top<=event.y_root<top+height):close()
        active=next((button for button in buttons if button.selected),buttons[0] if buttons else None)
        def focus_active():
            for button in buttons:
                button.keyboard_focus=button is active;button.highlight(False)
            if active:active.focus_set()
        def step(event,delta):
            nonlocal active
            if not buttons:return 'break'
            active=buttons[((buttons.index(active) if active in buttons else -1)+delta)%len(buttons)]
            focus_active();return 'break'
        def endpoint(index):
            nonlocal active
            if buttons:active=buttons[index];focus_active()
            return 'break'
        def cancel_key(event=None):close();return 'break'
        def confirm_key(event=None):
            if active:active.invoke()
            return 'break'
        handlers={'<Escape>':cancel_key,'<Down>':lambda e:step(e,1),'<Up>':lambda e:step(e,-1),
            '<Home>':lambda e:endpoint(0),'<End>':lambda e:endpoint(-1),'<Return>':confirm_key,'<space>':confirm_key}
        self.menu_keys=handlers
        for button in buttons:
            button.bind('<Return>',confirm_key);button.bind('<space>',confirm_key)
        w.bind('<Button-1>',outside)
        for sequence,handler in handlers.items():
            w.bind(sequence,handler)
            # Activating the owner window must not strand an open menu or let
            # Escape close an enclosing dialog. Restore its exact bindings.
            old=parent.bind(sequence);token=parent.bind(sequence,handler)
            parent_keys[sequence]=(old,token)
        w.protocol('WM_DELETE_WINDOW',close);w.update_idletasks();w.pulse_card.resize();w.deiconify();w.lift();w.focus_force();w.grab_set()
        focus_active()
        self.draw()
        return w

class OutlineButton(Surface):
    def __init__(self,p,parent,title,command):
        super().__init__(parent,p.scale,fill=BG,padx=0,pady=0)
        self.clip_radius=8
        self.p,self.command,self.hovered=p,command,False;self.configure(width=p.px(96),height=p.px(32),takefocus=True,cursor='hand2');self.pack_propagate(False)
        self.arrow=photo(self,render_asset('chevron-left.svg',p.px(14),p.px(14),p.scale))
        icon=tk.Label(self.inner,image=self.arrow,bg=BG,bd=0);icon.place(x=p.px(10),y=p.px(9),width=p.px(14),height=p.px(14))
        label=p.label(self.inner,title,13,INK);label.place(x=p.px(32),y=p.px(6),height=p.px(20))
        for widget in (self,self.back,self.inner,icon,label):widget.bind('<Button-1>',lambda _:self.invoke())
        self.bind('<Return>',lambda _:self.invoke());self.bind('<space>',lambda _:self.invoke())
        self.bind('<FocusIn>',self.draw);self.bind('<FocusOut>',self.draw)
        self.bind('<Enter>',lambda _:self.hover(True));self.bind('<Leave>',lambda _:self.hover(False))
    def invoke(self):self.focus_set();self.command();return 'break'
    def hover(self,value):self.hovered=value;self.draw()
    def draw(self,event=None):
        width,height=self.winfo_width(),self.winfo_height()
        if width<2 or height<2:return
        from strip_renderer import Renderer
        renderer=Renderer(width,self.scale,height=height)
        try:
            renderer.rounded(.5,.5,width/self.scale-1,height/self.scale-1,8,BG,theme.current() if self.focus_get()==self else '#a9bfdc' if self.hovered else '#d8e2f0')
            self.art=photo(self,renderer.png());self.back.configure(image=self.art)
        finally:renderer.close()

class ThemeSelector(tk.Frame):
    def __init__(self,p,parent,command):
        super().__init__(parent,bg=theme.color(BG),width=p.px(88),height=p.px(34),takefocus=True,cursor='hand2')
        self.p,self.command,self.title,self.expanded=p,command,'',False
        self.hovered=False;self.back=tk.Label(self,bg=theme.color(BG),bd=0);self.back.place(x=0,y=0,relwidth=1,relheight=1)
        self.dot=tk.Canvas(self,bg=theme.color(BG),bd=0,highlightthickness=0,width=p.px(12),height=p.px(12));self.dot.place(x=p.px(6),y=p.px(11))
        self.label=p.label(self,'',13,MUTED);self.label.place(x=p.px(26),y=p.px(7),height=p.px(20))
        self.arrow=tk.Label(self,bg=theme.color(BG),bd=0);self.arrow.place(x=p.px(74),y=p.px(10),width=p.px(14),height=p.px(14))
        for widget in (self,self.back,self.dot,self.label,self.arrow):
            widget.bind('<Button-1>',lambda _:self.invoke());widget.bind('<Enter>',lambda _:self.hover(True));widget.bind('<Leave>',lambda _:self.hover(False))
        self.bind('<Return>',lambda _:self.invoke());self.bind('<space>',lambda _:self.invoke())
        self.bind('<Configure>',self.draw);self.bind('<FocusIn>',self.draw);self.bind('<FocusOut>',self.draw)
        self.redraw()
    def invoke(self):self.focus_set();self.command();return 'break'
    def hover(self,value):self.hovered=value;self.draw()
    def draw(self,event=None):
        width,height=self.winfo_width(),self.winfo_height()
        if width<2 or height<2:return
        from strip_renderer import Renderer
        r=Renderer(width,self.p.scale,height=height)
        try:
            r.rounded(.5,.5,width/self.p.scale-1,height/self.p.scale-1,8,BG,
                theme.current() if self.expanded or self.focus_get()==self else '#a9bfdc' if self.hovered else None)
            self.back_art=photo(self,r.png());self.back.configure(image=self.back_art)
        finally:r.close()
    def cget(self,key):
        if key=='text':return self.title
        if key=='expanded':return self.expanded
        return super().cget(key)
    def configure(self,cnf=None,**kw):
        if cnf is not None:return super().configure(cnf,**kw)
        if 'text' in kw:self.title=kw.pop('text');self.label.configure(text=self.title)
        if 'expanded' in kw:self.expanded=kw.pop('expanded')
        result=super().configure(**kw)
        if hasattr(self,'arrow'):self.redraw()
        return result
    def redraw(self):
        from strip_renderer import Renderer
        r=Renderer(self.p.px(12),self.p.scale,height=self.p.px(12))
        try:r.ellipse(1,1,10,10,theme.current(),True);self.dot_art=photo(self.dot,r.png());self.dot.delete('all');self.dot.create_image(0,0,anchor='nw',image=self.dot_art)
        finally:r.close()
        self.arrow_art=photo(self.arrow,render_asset('chevron-up.svg' if self.expanded else 'chevron-down.svg',self.p.px(14),self.p.px(14),self.p.scale));self.arrow.configure(image=self.arrow_art);self.draw()

class TextInput(Surface):
    def __init__(self,p,parent,variable,width=100):
        super().__init__(parent,p.scale,fill=BG,padx=12,pady=0)
        self.p=p;self.configure(width=p.px(width),height=p.px(36));self.pack_propagate(False)
        self.entry=tk.Entry(self.inner,textvariable=variable,font=(family(),-p.px(ui.CONTROL_SIZE)),bg=BG,fg=INK,insertbackground=theme.current(),relief='flat',bd=0,highlightthickness=0)
        self.entry.pack(fill='both',expand=True);self.entry.bind('<FocusIn>',self.draw);self.entry.bind('<FocusOut>',self.draw)
    def draw(self,event=None):
        if not hasattr(self,'entry'):return
        width,height=self.winfo_width(),self.winfo_height()
        if width<2 or height<2:return
        from strip_renderer import Renderer
        r=Renderer(width,self.scale,height=height)
        try:
            r.rounded(.5,.5,width/self.scale-1,height/self.scale-1,8,BG,theme.current() if self.entry.focus_get()==self.entry else '#d8e2f0');self.art=photo(self,r.png());self.back.configure(image=self.art)
        finally:r.close()

def modal(p,title):
    # Like the settings panel, use an independent root. A transient owned
    # Toplevel can be hidden behind the floating parent on activation.
    p.modal_open=True
    w=tk.Tk();w.withdraw();w.title(title);w.overrideredirect(True);w.configure(bg=theme.color(BG));w.resizable(False,False);w.attributes('-topmost',True)
    w.report_callback_exception=p.window.report_callback_exception
    from panel_chrome import PopupCard
    w.pulse_card=PopupCard(w,p.scale,padx=22,pady=20);frame=w.pulse_card.body
    dialogs=getattr(p,'dialogs',None)
    if dialogs is None:p.dialogs=set();dialogs=p.dialogs
    dialogs.add(w);was_disabled=bool(p.window.attributes('-disabled'));p.window.attributes('-disabled',True)
    p.label(frame,title,17,bold=True).pack(fill='x',pady=(0,p.px(12)))
    closed=False
    def close():
        nonlocal closed
        if closed:return
        closed=True
        dialogs.discard(w);p.modal_open=bool(dialogs)
        try:
            w.grab_release()
            w.pulse_card.close();w.destroy()
            if p.window.winfo_exists():
                p.window.attributes('-disabled',was_disabled)
                if not getattr(p,'closed',False):p.window.focus_force()
        except tk.TclError:pass
    w.pulse_close=close
    w.protocol('WM_DELETE_WINDOW',close);w.bind('<Escape>',lambda _:close())
    return w,frame,close

def show_modal(p,w):
    w.update_idletasks();area=p.owner.win.work_area(p.hwnd);width=min(max(p.px(300),w.winfo_reqwidth()),area.width);height=min(w.winfo_reqheight(),area.height)
    x=max(area.left,min(p.window.winfo_rootx()+(p.window.winfo_width()-width)//2,area.right-width));y=max(area.top,min(p.window.winfo_rooty()+(p.window.winfo_height()-height)//2,area.bottom-height))
    w.geometry(f'{width}x{height}+{x}+{y}');w.update_idletasks();w.pulse_card.resize();w.deiconify();w.lift();w.focus_force();w.grab_set()
    if getattr(p.owner.args,'review_instance',False):
        # Expose this app's review dialog as its own automation target. Inputs
        # must activate the dialog rather than raising its floating parent.
        hwnd=p.owner.win.top_level(w.winfo_id());extended=p.owner.win.get_long(hwnd,-20)
        p.owner.win.own_overlay(hwnd,None)
        p.owner.win.set_long(hwnd,-20,(extended & ~0x80 & ~0x08000000) | 0x40000)

def info(p,title,text):
    w,frame,close=modal(p,title)
    p.label(frame,text,13,MUTED,wraplength=p.px(350),justify='left').pack(fill='x')
    button=p.button(frame,'知道了',close,dialog=True);button.pack(anchor='e',pady=(p.px(18),0))
    show_modal(p,w);button.focus_force()

def hours_dialog(p,current,apply):
    w,frame,close=modal(p,'自定义统计范围')
    p.label(frame,'1–168 小时，最多 7 天',12,MUTED).pack(fill='x')
    row=tk.Frame(frame,bg=theme.color(BG));row.pack(fill='x',pady=p.px(16))
    draft=tk.StringVar(master=w,value=str(current));field=TextInput(p,row,draft,width=88);field.pack(side='left');entry=field.entry;p.label(row,'小时',13,MUTED).pack(side='left',padx=p.px(8))
    error=p.label(frame,'',12,ACCENT);error.pack(fill='x')
    def confirm():
        raw=draft.get().strip()
        if not raw.isascii() or not raw.isdecimal() or not 1<=int(raw)<=168:error.configure(text='请输入 1–168 的整数小时。');return
        value=int(raw);close();apply(value)
    actions=tk.Frame(frame,bg=theme.color(BG));actions.pack(fill='x',pady=(p.px(14),0))
    p.button(actions,'应用',confirm,dialog=True).pack(side='right');p.button(actions,'取消',close,quiet=True,dialog=True).pack(side='right',padx=(0,p.px(10)))
    entry.bind('<Return>',lambda _:confirm());show_modal(p,w);entry.focus_set();entry.selection_range(0,'end')
    w.hours_entry=entry;w.apply_value=confirm;w.cancel_value=close
    return w

def session_dialog(p):
    import thread_catalog
    w,frame,close=modal(p,'选择固定会话')
    p.label(frame,'确认前，当前统计对象保持不变。',12,MUTED).pack(fill='x')
    search=tk.StringVar(master=w)
    from panel_widgets import SearchField
    field=SearchField(frame,search,p.scale);field.pack(fill='x',pady=p.px(12));entry=field.entry
    style=ttk.Style(w);style.configure('PulseV19.Treeview',font=(family(),-p.px(14)),rowheight=p.px(36),background=theme.color(BG),fieldbackground=theme.color(BG),foreground=theme.color(INK),borderwidth=0)
    style.layout('PulseV19.Treeview',[('Treeview.treearea',{'sticky':'nswe'})])
    style.map('PulseV19.Treeview',background=[('selected',theme.color('#f1f5fc'))],foreground=[('selected',theme.current())])
    from scroll_rail import SlimScrollbar
    list_host=tk.Frame(frame,bg=theme.color(BG));list_host.pack(fill='both',expand=True)
    area=p.owner.win.work_area(p.hwnd);visible_rows=max(3,min(7,int(area.height/p.scale-260)//36))
    tree=ttk.Treeview(list_host,show='tree',selectmode='browse',height=visible_rows,style='PulseV19.Treeview');tree.column('#0',width=p.px(340));tree.pack(side='left',fill='both',expand=True)
    rail=SlimScrollbar(list_host,tree.yview,p.scale);rail.pack(side='right',fill='y');tree.configure(yscrollcommand=rail.set)
    result=p.label(frame,'',12,MUTED);result.pack(fill='x',pady=p.px(8))
    catalog=thread_catalog.recent(p.owner.args.codex_home.resolve(),limit=None,work_only=True);matches=[]
    def confirm():
        selected=tree.selection()
        if not selected:return
        item=next((i for i in thread_catalog.recent(p.owner.args.codex_home.resolve(),limit=None,work_only=True) if i['id']==selected[0]),None)
        if item is None:result.configure(text='该工作会话已不可用，请重新选择。');return
        p.owner.select_thread(item['id'],item['title']);close();p.show_tab('strip')
    actions=tk.Frame(frame,bg=theme.color(BG));actions.pack(fill='x',pady=(p.px(8),0))
    confirm_button=p.button(actions,'确认固定',confirm,dialog=True);confirm_button.pack(side='right');confirm_button.configure(state='disabled');p.button(actions,'取消',close,quiet=True,dialog=True).pack(side='right',padx=(0,p.px(10)))
    def filter_rows(*_):
        nonlocal matches
        matches=[i for i in catalog if search.get().strip().casefold() in i['title'].casefold()]
        tree.delete(*tree.get_children())
        for i in matches:tree.insert('','end',iid=i['id'],text=i['title']+('   当前' if i['id']==p.owner.binding.identity else ''))
        result.configure(text=f'{len(matches)} 项' if matches else '没有符合条件的未归档工作会话');confirm_button.configure(state='disabled')
    search.trace_add('write',filter_rows);tree.bind('<<TreeviewSelect>>',lambda _:confirm_button.configure(state='normal' if tree.selection() else 'disabled'))
    tree.bind('<Return>',lambda _:confirm());filter_rows();show_modal(p,w);entry.focus_set()
    w.session_tree=tree;w.session_scroll=rail;w.search=search;w.confirm_button=confirm_button;w.confirm_session=confirm;w.cancel_session=close
    return w
