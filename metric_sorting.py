"""Visible, cancellable metric ordering; preferences change only on drop."""
import time
import tkinter as tk
import theme


class MetricSorter:
    def __init__(self,panel,host,rows,commit):
        self.panel,self.host,self.rows,self.commit=panel,host,dict(rows),commit
        self.order=list(self.rows);self.preview=list(self.order)
        self.height=panel.px(40);self.active=None;self.dragging=False
        self.animation=None;self.scroll_job=None;self.positions={}
        self.slot=tk.Frame(host,bg=theme.color('#f3f1fa'),bd=0)
        self.marker=tk.Frame(self.slot,bg=theme.current(),height=panel.px(2));self.marker.pack(fill='x')
        self.host.bind('<Unmap>',lambda e:self.cancel() if e.widget is host else None,add='+')
        self.host.bind('<Destroy>',lambda e:self.cancel() if e.widget is host else None,add='+')
        self.sync(self.order)

    def bind(self,key,handle):
        handle.bind('<ButtonPress-1>',lambda e:self.start(key,handle,e))
        handle.bind('<B1-Motion>',self.move)
        handle.bind('<ButtonRelease-1>',self.drop)
        handle.bind('<Escape>',self.cancel)
        handle.bind('<FocusOut>',lambda e:self.cancel() if self.active==key else None,add='+')

    def sync(self,order):
        self.cancel()
        self.order=list(order);self.preview=list(order)
        self.host.configure(height=self.height*len(order))
        self.arrange(False)

    def arrange(self,animate=True):
        self.stop_animation()
        target={key:i*self.height for i,key in enumerate(self.preview) if key!=self.active or not self.dragging}
        if not animate or not getattr(self.panel.owner,'animations',True):
            for key,y in target.items():self.place(key,y)
            return
        start={key:self.positions.get(key,y) for key,y in target.items()};at=time.monotonic()
        def frame():
            self.animation=None
            if not self.host.winfo_exists():return
            ratio=min(1,(time.monotonic()-at)/.12);eased=1-(1-ratio)**3
            for key,y in target.items():self.place(key,start[key]+(y-start[key])*eased)
            if ratio<1:self.animation=self.host.after(16,frame)
        frame()

    def place(self,key,y):
        self.positions[key]=float(y)
        self.rows[key].place(x=0,y=round(y),relwidth=1,height=self.height)

    def start(self,key,handle,event):
        self.cancel();self.active=key;self.handle=handle
        self.origin=(event.x_root,event.y_root);self.pointer=self.origin
        self.offset=event.y_root-self.rows[key].winfo_rooty()
        self.preview=list(self.order);self.dragging=False
        handle.focus_set();handle.grab_set()
        return 'break'

    def move(self,event):
        if self.active is None:return
        self.pointer=(event.x_root,event.y_root)
        distance=(event.x_root-self.origin[0])**2+(event.y_root-self.origin[1])**2
        if not self.dragging and distance<max(4,self.panel.px(4))**2:return 'break'
        if not self.dragging:
            self.dragging=True
            self.rows[self.active].configure(highlightthickness=1,highlightbackground=theme.current())
            self.rows[self.active].lift()
        self.preview_pointer()
        self.edge_scroll()
        return 'break'

    def preview_pointer(self):
        y=self.pointer[1]-self.host.winfo_rooty()-self.offset
        y=max(0,min(y,(len(self.order)-1)*self.height))
        index=max(0,min(len(self.order)-1,int((y+self.height/2)//self.height)))
        changed=list(self.order);changed.remove(self.active);changed.insert(index,self.active)
        if changed!=self.preview:
            self.preview=changed;self.arrange()
        self.slot.configure(bg=theme.color('#f3f1fa'));self.marker.configure(bg=theme.current())
        self.slot.place(x=0,y=index*self.height,relwidth=1,height=self.height);self.slot.lower()
        self.place(self.active,y);self.rows[self.active].lift()

    def edge_scroll(self):
        if self.scroll_job is not None:return
        canvas=getattr(self.panel,'content',None)
        if not canvas:return
        def scroll():
            self.scroll_job=None
            if not self.dragging:return
            y=self.pointer[1];top=canvas.winfo_rooty();bottom=top+canvas.winfo_height()
            step=-1 if y<top+self.panel.px(24) else 1 if y>bottom-self.panel.px(24) else 0
            before=canvas.yview()
            if step and ((step<0 and before[0]>0) or (step>0 and before[1]<1)):
                canvas.yview_scroll(step,'units');canvas.update_idletasks();self.preview_pointer()
                self.scroll_job=self.host.after(45,scroll)
        scroll()

    def inside(self,event):
        canvas=getattr(self.panel,'content',self.host)
        return (self.host.winfo_rootx()<=event.x_root<self.host.winfo_rootx()+self.host.winfo_width()
                and max(self.host.winfo_rooty(),canvas.winfo_rooty())<=event.y_root
                <min(self.host.winfo_rooty()+self.host.winfo_height(),canvas.winfo_rooty()+canvas.winfo_height()))

    def drop(self,event):
        if self.active is None:return
        # Native input can coalesce the last motion before button release.
        if self.inside(event):self.move(event)
        accepted=self.dragging and self.inside(event)
        result=list(self.preview) if accepted else list(self.order)
        changed=result!=self.order
        self.finish();self.order=result;self.preview=list(result);self.arrange()
        if changed:self.commit(result)
        return 'break'

    def stop_animation(self):
        if self.animation is not None:
            try:self.host.after_cancel(self.animation)
            except tk.TclError:pass
            self.animation=None

    def finish(self):
        self.stop_animation()
        if self.scroll_job is not None:
            try:self.host.after_cancel(self.scroll_job)
            except tk.TclError:pass
            self.scroll_job=None
        if self.active is not None:
            try:
                self.rows[self.active].configure(highlightthickness=0)
                if self.handle.grab_current()==self.handle:self.handle.grab_release()
            except tk.TclError:pass
        try:self.slot.place_forget()
        except tk.TclError:pass
        self.active=None;self.dragging=False

    def cancel(self,event=None):
        if self.active is not None or self.animation is not None:
            self.finish();self.preview=list(self.order)
            try:self.arrange(False)
            except tk.TclError:pass
        return 'break'
