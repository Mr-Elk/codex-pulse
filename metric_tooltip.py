"""Read-only metric hover cards, including when the strip passes clicks through."""
import time
import tkinter as tk
import theme
from font_policy import widget_family as family
from product_data import tooltip

class MetricTooltip:
    def __init__(self,owner):self.owner=owner;self.window=None;self.key=None;self.pending=None;self.entered=0;self.signature=None;self.leave_at=0;self.presentation=None
    def hide(self):
        self.key=None;self.pending=None;self.presentation=None
        if self.window:self.window.withdraw()
    def show(self,key,bounds):
        owner=self.owner;data=tooltip(key,owner.snapshot,owner.quota_snapshot,owner.quota_preferences,owner.bound_title)
        signature=repr(data),owner.scale,theme.current()
        presentation=(key,signature,bounds)
        if presentation==self.presentation:return
        if not self.window:
            # Independent Tk root: creating an owned Toplevel would repaint the
            # withdrawn root of the externally drawn layered statistics HWND.
            self.window=tk.Tk();self.window.withdraw();self.window.overrideredirect(True);self.window.configure(bg='#dbe3ef');self.window.title('Codex Pulse 指标详情')
            self.window.report_callback_exception=owner.root.report_callback_exception
            self.window.update_idletasks();self.hwnd=owner.win.top_level(self.window.winfo_id())
            # Never make the layered strip the native owner of a Tk window.
            # Tk restacking an owned tooltip can reorder the separate blur
            # and foreground windows when the tooltip changes size.
            owner.win.decorate_overlay(self.hwnd)
            if getattr(owner.args,'review_instance',False):
                extended=owner.win.get_long(self.hwnd,-20)
                owner.win.set_long(self.hwnd,-20,(extended & ~0x80) | 0x40000)
        revealing=self.window.state()=='withdrawn' or self.key!=key
        desktop=owner.display_mode=='desktop';target=(getattr(owner,'target',None) or {}).get('hwnd')
        context=(desktop,None if desktop else target)
        if context!=getattr(self,'window_context',None):
            owner.win.own_overlay(self.hwnd,None)
            self.window.attributes('-topmost',desktop)
            owner.win.own_overlay(self.hwnd,context[1]);self.window_context=context
        if not hasattr(self,'labels'):
            from panel_chrome import PopupCard
            s=owner.scale;self.card=PopupCard(self.window,s,padx=1,pady=1);body=self.card.body
            content=tk.Frame(body,bg='#ffffff',width=round(210*s));content.pack(fill='both',expand=True,padx=round(13*s),pady=round(12*s))
            def label(parent,text='',size=12,bold=False,color='#607088',**kw):
                return tk.Label(parent,text=text,bg='#ffffff',fg=color,font=(family(),-round(size*s),'bold' if bold else 'normal'),bd=0,padx=0,pady=0,**kw)
            head=tk.Frame(content,bg='#ffffff',height=round(20*s));head.pack(fill='x');head.pack_propagate(False)
            title=label(head,size=13,bold=True,anchor='w');title.place(x=0,y=0,relwidth=.64,height=round(20*s))
            status=label(head,anchor='e');status.place(relx=1,anchor='ne',y=0,relwidth=.36,height=round(18*s))
            from panel_runtime import Number
            from types import SimpleNamespace
            policy=SimpleNamespace(px=lambda n:round(n*s),label=lambda parent,value,size=12,color='#233955',bold=False,bg='#ffffff',**kw:label(parent,value,size,bold,color=color,**kw))
            reading=Number(policy,content,size=20,height=26,unit_size=12,bg='#ffffff');reading.pack(fill='x',pady=(round(6*s),round(8*s)));reading.configure(height=round(26*s))
            facts=tk.Frame(content,bg='#ffffff');facts.pack(fill='x');facts.grid_columnconfigure(1,weight=1)
            description=label(content,wraplength=round(210*s),justify='left',anchor='w');description.pack(fill='x',pady=(round(8*s),round(8*s)))
            foot=label(content,wraplength=round(210*s),justify='left',anchor='w');foot.pack(fill='x',pady=(round(8*s),0))
            self.labels={'title':title,'status':status,'reading':reading,'facts':facts,'rows':[],'body':description,'foot':foot};self.make_label=label
        if signature!=self.signature:
            from panel_runtime import update
            v=self.labels;s=owner.scale
            for field in ('title','status','body','foot'):update(v[field],text=data[field],fg=theme.current() if field in ('title','status') else '#607088')
            v['reading'].set(data['value'])
            while len(v['rows'])<len(data['rows']):
                i=len(v['rows']);name=self.make_label(v['facts'],anchor='nw',wraplength=round(62*s));detail=self.make_label(v['facts'],anchor='nw',wraplength=round(140*s),justify='left')
                name.grid(row=i,column=0,sticky='nw',padx=(0,round(8*s)),pady=(0,round(4*s)));detail.grid(row=i,column=1,sticky='nw',pady=(0,round(4*s)));v['rows'].append((name,detail))
            for i,(name,detail) in enumerate(v['rows']):
                if i<len(data['rows']):
                    name.grid();detail.grid();update(name,text=data['rows'][i][0]);update(detail,text=data['rows'][i][1],fg='#233955')
                else:name.grid_remove();detail.grid_remove()
            self.signature=signature
        self.window.update_idletasks();hwnd=self.hwnd
        area=owner.win.work_area(owner.hwnd);width,height=round(238*owner.scale),self.window.winfo_reqheight();left=max(area.left+8,min(bounds.left+(bounds.width-width)//2,area.right-width-8));top=bounds.top-height-10
        if top<area.top:top=min(bounds.bottom+10,area.bottom-height-8)
        self.window.geometry(f'{width}x{height}+{left}+{max(area.top+8,top)}')
        self.window.update_idletasks();self.card.resize()
        if self.window.state()=='withdrawn':self.window.deiconify()
        owner.win.show_without_focus(hwnd,__import__('overlay_geometry').Rect(left,max(area.top+8,top),left+width,max(area.top+8,top)+height),raise_window=revealing);self.key=key;self.presentation=presentation
    def poll(self):
        if getattr(self.owner,'layout_transition',False):self.hide();return
        o=self.owner
        panel=getattr(o,'settings_panel',None)
        # menu_open also keeps the strip alive while ordinary settings are open.
        # Only an actual modal/dropdown should suppress read-only hover cards.
        blocked=bool(getattr(panel,'modal_open',False)) if panel is not None and not getattr(panel,'closed',False) else o.menu_open
        if not o.visible or not o.last_bounds or blocked or o.drag or o.stop.is_set():self.hide();return
        point=o.win.cursor_position();rect=o.last_bounds;key=None
        if point and rect.left<=point[0]<rect.right and rect.top<=point[1]<rect.bottom:
            x=(point[0]-rect.left)/(o.scale*o.font_size/15)
            key=next((c['key'] for c in o.layout if c['left']<=x<c['right']),None)
        if key:
            self.leave_at=0
            if self.pending!=key:self.pending=key;self.entered=time.monotonic()
            if time.monotonic()-self.entered>=.18:
                from overlay_geometry import Rect
                cell=next(c for c in o.layout if c['key']==key);factor=o.scale*o.font_size/15
                anchor=Rect(rect.left+round(cell['left']*factor),rect.top,rect.left+round(cell['right']*factor),rect.bottom)
                self.show(key,anchor)
        elif self.window and self.key:
            if not self.leave_at:self.leave_at=time.monotonic()
            if time.monotonic()-self.leave_at>.15:self.hide()
        else:self.pending=None
    def close(self):
        if self.window:
            if hasattr(self,'card'):self.card.close()
            self.window.destroy();self.window=None
