"""An inline, draft-first color picker using the panel's own vector renderer."""
import base64
import colorsys
import re
import tkinter as tk

from font_policy import widget_family as family
from panel_widgets import Surface, BG, MUTED
import theme


def valid_hex(value):
    return isinstance(value,str) and re.fullmatch(r"#[0-9a-fA-F]{6}",value.strip()) is not None


def hsv_hex(h,s,v):
    return "#"+"".join(f"{round(c*255):02x}" for c in colorsys.hsv_to_rgb(h,s,v))


def hex_hsv(value):
    return colorsys.rgb_to_hsv(*(int(value[i:i+2],16)/255 for i in (1,3,5)))


def field_png(width,height,scale,h,s,v,kind):
    """Literal HSV gradients and antialiased corners/cursor; never recolored."""
    from strip_renderer import Renderer,RectF,P,F,C,W,bind,call
    r=Renderer(width,scale,height=height)
    try:
        bind("GdipCreateLineBrushFromRect",[C.POINTER(RectF),W.UINT,W.UINT,C.c_int,C.c_int,C.POINTER(P)])
        bind("GdipSetClipPath",[P,P,C.c_int]);bind("GdipResetClip",[P])
        pad=6
        w,extent=width/scale-2*pad,height/scale-2*pad
        path=r.new("GdipCreatePath","GdipDeletePath",0)
        radius=min(8,extent/2)
        for x,y,a in ((pad,pad,180),(pad+w-radius*2,pad,270),(pad+w-radius*2,pad+extent-radius*2,0),(pad,pad+extent-radius*2,90)):
            call("GdipAddPathArc",path,x,y,radius*2,radius*2,a,90)
        call("GdipClosePathFigure",path)
        bind("GdipFillRectangle",[P,P,F,F,F,F])
        # Clip on the 3x working canvas once. Repeated antialiased fills of the
        # same path blend its white edge into the black end of the gradient.
        call("GdipSetClipPath",r.g,path,0)
        def gradient(x,width,left,right,vertical=False):
            brush=r.new("GdipCreateLineBrushFromRect","GdipDeleteBrush",
                        C.byref(RectF(x,pad,width,extent)),left,right,int(vertical),0)
            call("GdipFillRectangle",r.g,brush,x,pad,width,extent)
        if kind=="sv":
            pure=int("ff"+hsv_hex(h,1,1)[1:],16)
            gradient(pad,w,0xffffffff,pure)
            gradient(pad,w,0x00000000,0xff000000,True)
            x,y=pad+s*w,pad+(1-v)*extent
        else:
            for i in range(6):
                x=pad+i*w/6
                brush=r.new("GdipCreateLineBrushFromRect","GdipDeleteBrush",
                            C.byref(RectF(x,pad,w/6+.01,extent)),
                            int("ff"+hsv_hex(i/6,1,1)[1:],16),int("ff"+hsv_hex((i+1)/6,1,1)[1:],16),0,0)
                call("GdipFillRectangle",r.g,brush,x,pad,w/6+.01,extent)
            x,y=pad+h*w,pad+extent/2
        call("GdipResetClip",r.g)
        r.ellipse(x-4.5,y-4.5,9,9,"#ffffff",thickness=2)
        pen=r.new("GdipCreatePen1","GdipDeletePen",0xff515464,.8,0)
        call("GdipDrawEllipse",r.g,pen,x-5.8,y-5.8,11.6,11.6)
        return r.png()
    finally:
        r.close()


class ColorField(tk.Canvas):
    def __init__(self,parent,editor,kind,height):
        self.editor,self.kind=editor,kind
        super().__init__(parent,width=1,height=round(height*editor.scale),bg=theme.color(BG),
                         bd=0,highlightthickness=0,takefocus=True,cursor="crosshair")
        self.bind("<Configure>",lambda _:self.redraw())
        self.bind("<Button-1>",self.pick);self.bind("<B1-Motion>",self.pick)
        for key,dx,dy in (("Left",-1,0),("Right",1,0),("Up",0,-1),("Down",0,1)):
            self.bind("<"+key+">",lambda _,dx=dx,dy=dy:self.step(dx,dy))

    def redraw(self):
        w,h=self.winfo_width(),self.winfo_height()
        if min(w,h)<10:return
        self.png=field_png(w,h,self.editor.scale,*self.editor.hsv,self.kind)
        self.art=tk.PhotoImage(master=self,data=base64.b64encode(self.png))
        self.delete("all");self.create_image(0,0,anchor="nw",image=self.art)

    def pick(self,event):
        self.focus_set()
        pad=6*self.editor.scale
        x=max(0,min(1,(event.x-pad)/max(1,self.winfo_width()-2*pad)))
        y=max(0,min(1,(event.y-pad)/max(1,self.winfo_height()-2*pad)))
        h,s,v=self.editor.hsv
        self.editor.set_hsv(x,s,v) if self.kind=="hue" else self.editor.set_hsv(h,x,1-y)
        return "break"

    def step(self,dx,dy):
        h,s,v=self.editor.hsv
        self.editor.set_hsv((h+dx/360)%1,s,v) if self.kind=="hue" else self.editor.set_hsv(h,max(0,min(1,s+dx*.01)),max(0,min(1,v-dy*.01)))
        return "break"


class ColorEditor(tk.Frame):
    def __init__(self,parent,scale,initial,on_apply,button,fill):
        super().__init__(parent,bg=theme.color(fill),bd=0)
        self.scale,self.fill,self.on_apply=scale,fill,on_apply
        self.applied=initial.lower();self.hsv=hex_hsv(initial);self.opened=False;self.updating=False
        self.value=tk.StringVar(master=self,value=initial.upper())
        row=tk.Frame(self,bg=theme.color(fill));row.pack(fill="x")
        font=(family(),-round(12*scale))
        tk.Label(row,text="自定义",font=font,bg=theme.color(fill),fg=theme.color(MUTED),bd=0).pack(side="left",padx=(0,round(8*scale)))
        field=Surface(row,scale,fill=BG,padx=10,pady=6)
        field.configure(width=round(110*scale),height=round(34*scale));field.pack_propagate(False)
        field.pack(side="left",padx=(0,round(8*scale)))
        self.entry=tk.Entry(field.inner,textvariable=self.value,font=(family(),-round(13*scale)),
                            bg=BG,fg="#35364b",insertbackground=theme.color("#7865d6"),relief="flat",bd=0,highlightthickness=0)
        self.entry.pack(fill="both",expand=True)
        self.entry.bind("<Return>",lambda _:self.apply())
        self.swatch=tk.Canvas(row,width=round(34*scale),height=round(34*scale),bg=theme.color(fill),bd=0,
                              highlightthickness=0,cursor="hand2",takefocus=True)
        self.swatch.pack(side="left",padx=(0,round(8*scale)))
        self.swatch.bind("<Configure>",lambda _:self.redraw())
        for event in ("<Button-1>","<Return>","<space>"):
            self.swatch.bind(event,lambda _:self.toggle_picker())
        self.apply_button=button(row,"应用",self.apply);self.apply_button.pack(side="left")
        self.status=tk.Label(self,text="",font=(family(),-round(12*scale)),bg=theme.color(fill),fg=theme.color(MUTED),bd=0,anchor="w")
        self.status.pack(fill="x",pady=(round(7*scale),0))
        self.picker=Surface(self,scale,fill=BG,padx=8,pady=8)
        self.plane=ColorField(self.picker.inner,self,"sv",126);self.plane.pack(fill="x")
        self.hue=ColorField(self.picker.inner,self,"hue",24);self.hue.pack(fill="x",pady=(round(4*scale),0))
        actions=tk.Frame(self.picker.inner,bg=BG);actions.pack(fill="x")
        tk.Label(actions,text="拖动选色，点击应用后保存",font=(family(),-round(12*scale)),bg=BG,fg=theme.color(MUTED),bd=0).pack(side="left")
        button(actions,"取消",self.cancel,quiet=True).pack(side="right")
        self.trace=self.value.trace_add("write",self.edited)
        self.bind("<Destroy>",self.dispose)
        for widget in (self.entry,self.swatch,self.plane,self.hue):
            widget.bind("<Escape>",lambda _:self.escape())
        self.sync(initial,next((n for n,v in theme.PRESETS if v==initial),"自定义"),force=True)

    def dispose(self,event):
        if event.widget==self:self.value.trace_remove("write",self.trace)

    def sync(self,value,name,force=False):
        value=value.lower()
        if value!=self.applied or force:
            self.applied=value;self.value.set(value.upper());self.hsv=hex_hsv(value)
            self.opened=False;self.picker.pack_forget()
            self.status.configure(text=name+"  "+value.upper(),fg=theme.color(MUTED))
            self.redraw()

    def edited(self,*_):
        value=self.value.get().strip()
        if valid_hex(value):
            if not self.updating:self.hsv=hex_hsv(value)
            self.status.configure(text="待应用  "+value.upper() if value.lower()!=self.applied else "当前颜色  "+value.upper(),fg=theme.color(MUTED))
            self.redraw()

    def set_hsv(self,h,s,v):
        self.hsv=h,s,v;self.updating=True
        try:self.value.set(hsv_hex(h,s,v).upper())
        finally:self.updating=False

    def redraw(self):
        from strip_renderer import Renderer,call
        w,h=self.swatch.winfo_width(),self.swatch.winfo_height()
        value=self.value.get().strip().lower()
        if not valid_hex(value):value=self.applied
        if min(w,h)>2:
            r=Renderer(w,self.scale,height=h)
            try:
                r.rounded(.6,.6,w/self.scale-1.2,h/self.scale-1.2,8,BG,"#e7e5ef")
                brush=r.new("GdipCreateSolidFill","GdipDeleteBrush",int("ff"+value[1:],16))
                # A literal inset color tile; all edges share the vector image.
                from strip_renderer import C,F,P,bind
                bind("GdipFillRectangle",[P,P,F,F,F,F])
                call("GdipFillRectangle",r.g,brush,7,7,w/self.scale-14,h/self.scale-14)
                self.swatch_png=r.png();self.art=tk.PhotoImage(master=self,data=base64.b64encode(self.swatch_png))
            finally:r.close()
            self.swatch.delete("all");self.swatch.create_image(0,0,anchor="nw",image=self.art)
        if self.opened:self.plane.redraw();self.hue.redraw()

    def toggle_picker(self):
        self.opened=not self.opened
        if self.opened:self.picker.pack(fill="x",pady=(round(8*self.scale),0));self.redraw()
        else:self.picker.pack_forget()
        return "break"

    def cancel(self):
        self.value.set(self.applied.upper());self.hsv=hex_hsv(self.applied)
        self.opened=False;self.picker.pack_forget();self.redraw()

    def escape(self):
        if self.opened:
            self.cancel()
            return "break"

    def apply(self):
        value=self.value.get().strip().lower()
        if not valid_hex(value):
            self.status.configure(text="请输入 #RRGGBB 格式的颜色",fg="#9a6b20");self.entry.focus_set()
            return "break"
        self.on_apply(value)
        self.opened=False;self.picker.pack_forget()
        self.sync(value,next((n for n,v in theme.PRESETS if v==value),"自定义"),force=True)
        return "break"
