"""Retained settings pages: a value update never recreates a page or its focus."""
import tkinter as tk
import theme

PAGE_ATTRS=('view_selector','metric_sorter','live_labels','metric_toggles','metric_variables','metric_rows','metric_count','select_all_button','metric_icons','metric_icon_key',
 'capsule_selectors','capsule_rows','capsule_help','binding_selector','session_current','session_kind','session_change',
 'scope_selector','hours_selector','mode_buttons','visibility_choice','font_segments','font_buttons',
 'theme_buttons','color_editor','theme_frame','theme_button','theme_row','color_theme_key')

def update(widget,**values):
    changed={key:value for key,value in values.items() if str(widget.cget(key))!=str(value)}
    if changed:widget.configure(**changed)

def show_page(p,tab):
    if tab=='session':tab='strip';p.strip_view='source'
    if tab not in ('strip','quota','display'):tab='strip'
    key=(tab,getattr(p,'strip_view','metrics') if tab=='strip' else '')
    cache=getattr(p,'page_cache',None)
    if cache is None:
        p.page_cache={};cache=p.page_cache;p.active_page=None
        p.body.destroy()
    if p.active_page==key:
        p.refresh();return
    if p.quota_job:p.window.after_cancel(p.quota_job);p.quota_job=None
    if p.catalog_job:p.window.after_cancel(p.catalog_job);p.catalog_job=None
    if p.active_page in cache:
        old=cache[p.active_page];old['scroll']=p.content.yview()[0]
        old['attrs']={name:getattr(p,name) for name in PAGE_ATTRS if hasattr(p,name)}
    for name in PAGE_ATTRS:
        if hasattr(p,name):delattr(p,name)
    p.tab=tab
    if key not in cache:
        body=tk.Frame(p.content,bg=theme.color('#ffffff'))
        body.bind('<Configure>',lambda _:p.update_scroll() if p.active_page==key else None)
        # Map the new page outside the viewport while the current page remains
        # visible. Images and geometry are ready before the visible swap.
        staging=p.content.create_window(-10000,-10000,window=body,anchor='nw',width=max(1,p.content.winfo_width()))
        p.body=body
        try:
            if tab=='strip':p.build_strip()
            elif tab=='display':p.build_display()
            else:
                from product_account import QuotaPanel
                p.quota_page=QuotaPanel(p)
            p.window.update_idletasks()
        finally:
            p.content.itemconfigure(staging,window='');p.content.delete(staging)
        cache[key]={'body':body,'scroll':0.,'attrs':{name:getattr(p,name) for name in PAGE_ATTRS if hasattr(p,name)}}
    else:
        p.body=cache[key]['body']
        for name,value in cache[key]['attrs'].items():setattr(p,name,value)
    p.active_page=key
    p.content.itemconfigure(p.body_item,window=p.body,width=max(1,p.content.winfo_width()))
    p.tabs.select(tab);p.update_scroll()
    # Geometry settles before restoring the existing page's scroll position.
    p.window.after_idle(lambda:p.content.yview_moveto(cache[key]['scroll']) if not p.closed and p.active_page==key else None)
    p.refresh()
    if tab=='quota':p.quota_job=p.window.after(1000,p.quota_tick)

class Number(tk.Frame):
    """One stable baseline with smaller units, as in the approved prototype."""
    def __init__(self,p,parent,size=28,height=40,unit_size=15,bg='#f8fbff'):
        super().__init__(parent,bg=theme.color(bg),height=p.px(height),bd=0)
        self.p,self.size,self.logical_height=p,size,height;self.value=None
        self.main=p.label(self,'—',size,bold=True,bg=bg)
        self.unit=p.label(self,'',unit_size,bg=bg)
        self.main.place(x=0,y=0,height=p.px(height));self.unit_size=unit_size
    def set(self,value,unit=None):
        if unit is None:
            text=str(value);unit='%' if text.endswith('%') else '';text=text[:-1] if unit else text
        else:text=str(value)
        signature=(text,unit)
        if self.value==signature:return
        self.value=signature;update(self.main,text=text);update(self.unit,text=unit)
        import tkinter.font as font
        width=font.Font(root=self.main,font=self.main.cget('font')).measure(text)
        self.main.place_configure(width=width)
        top=14 if self.logical_height==36 and self.unit_size==14 else {28:12,32:13,24:12,20:8}.get(self.size,self.logical_height-self.unit_size-8)
        if unit:self.unit.place(x=width+self.p.px(2),y=self.p.px(top),height=self.p.px({18:26,15:21,14:20,12:18}.get(self.unit_size,self.unit_size+6)))
        else:self.unit.place_forget()

def install(cls):cls.show_tab=show_page
