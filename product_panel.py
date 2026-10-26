"""Retained native settings using the measured v19 page geometry."""
import tkinter as tk
import theme
import ui_tokens as ui
from panel_widgets import Surface,Segmented,ModeCard,Checkbox,photo
from panel_runtime import update
from product_controls import Select,hours_dialog,session_dialog,info,ThemeSelector
from product_data import LABELS,metric_values
from quota_model import selected_group,selected_window
from quota_service import clean_config,METRIC_KEYS
from svg_art import render_asset
BG,INK,MUTED,ACCENT='#ffffff','#233955','#607088','#7865d6'

def box(p,parent,height,gap=0):
    f=tk.Frame(parent,bg=theme.color(BG),height=p.px(height));f.pack(fill='x',pady=(0,p.px(gap)));f.pack_propagate(False);return f

def text(p,parent,value,size=14,bold=False,color=INK,x=0,y=0,height=22,**kw):
    w=p.label(parent,value,size,color,bold=bold,**kw);w.place(x=p.px(x),y=p.px(y),height=p.px(height));return w

def heading(p,title,sub='',action=None):
    h=box(p,p.body,ui.TITLE_LINE+ui.TITLE_HELP_GAP+ui.HELP_LINE if sub else ui.TITLE_LINE,ui.SECTION_GAP if sub else ui.FIELD_GAP)
    text(p,h,title,ui.TITLE_SIZE,True,y=0 if sub else 2,height=ui.TITLE_LINE if sub else ui.LABEL_LINE)
    if sub:text(p,h,sub,ui.HELP_SIZE,color=MUTED,y=ui.TITLE_LINE+ui.TITLE_HELP_GAP,height=ui.HELP_LINE)
    if action:
        widget=action(h)
        if sub:widget.place(relx=1,anchor='ne',x=0,y=0)
        else:widget.place(relx=1,anchor='ne',x=0,y=p.px(1),height=p.px(ui.TEXT_ACTION_HEIGHT))
    return h

def row(p,parent,title,description='',gap=ui.FIELD_GAP):
    h=ui.LABEL_LINE+ui.DESCRIPTION_GAP+ui.HELP_LINE if description else ui.CONTROL_HEIGHT;r=box(p,parent,h,gap)
    text(p,r,title,ui.LABEL_SIZE,True,y=0 if description else (h-ui.LABEL_LINE)//2,height=ui.LABEL_LINE)
    if description:text(p,r,description,ui.HELP_SIZE,color=MUTED,y=ui.LABEL_LINE+ui.DESCRIPTION_GAP,height=ui.HELP_LINE)
    return r

def strip_view(p,value):
    # A navigation control belongs to its retained page. Do not leave the
    # destination label painted on the outgoing page while staging the next.
    active=getattr(p,'active_page',None)
    if active and active[0]=='strip' and hasattr(p,'view_selector'):
        p.view_selector.set(active[1])
    p.strip_view=value;p.show_tab('strip')

def metric_choices(p,key,cfg):
    other='capsule_secondary' if key=='capsule_primary' else 'capsule_primary'
    return ([('', '不显示')] if key=='capsule_secondary' else [])+[(k,f"最近 {cfg['hours']} 小时用量" if k=='recent' else LABELS[k],k==cfg[other]) for k in METRIC_KEYS]

def metric_icon_key(p):
    cfg=clean_config(p.owner.quota_preferences);window=selected_window(p.owner.quota_snapshot,cfg)
    return theme.current(),cfg['hours'],(window or {}).get('minutes')

def build_strip(p):
    owner=p.owner;view=getattr(p,'strip_view','metrics');p.strip_view=view;p.live_labels={}
    hints={'metrics':'勾选显示指标，拖动左侧手柄调整顺序。','capsule':'选择收起状态下显示的数据，最多两项。','source':'选择统计会话和账户用量范围。'}
    # The metrics toolbar's -6px source margin is represented by an 18px gap.
    def navigation(parent):
        p.view_selector=Select(p,parent,[('metrics','指标与顺序'),('capsule','收起状态'),('source','统计对象与范围')],view,lambda v:strip_view(p,v))
        return p.view_selector
    header=heading(p,'统计条',hints[view],navigation)
    if view=='metrics':
        header.pack_configure(pady=(0,p.px(18)));tools=box(p,p.body,24,6)
        p.metric_count=text(p,tools,'',12,color=MUTED,y=6,height=18)
        reset=p.button(tools,'恢复默认顺序',lambda:reset_order(p),quiet=True);reset.place(relx=1,anchor='ne')
        p.select_all_button=p.button(tools,'全选',lambda:select_all(p),quiet=True);p.select_all_button.place(relx=1,x=-(reset.draw_width+p.px(12)),anchor='ne')
        p.metric_toggles={};p.metric_variables={};p.metric_rows=[];p.metric_icons={};p.metric_icon_key=metric_icon_key(p)
        host=box(p,p.body,40*len(owner.metric_order));handles={}
        for key in owner.metric_order:
            line=tk.Frame(host,bg=theme.color(BG),height=p.px(40));handle=text(p,line,'⠿',14,color=MUTED,x=8,y=9,height=22,cursor='fleur')
            handle.configure(takefocus=True)
            handles[key]=handle
            handle.bind('<Up>',lambda e,k=key:move_order(p,k,-1));handle.bind('<Down>',lambda e,k=key:move_order(p,k,1))
            variable=tk.BooleanVar(master=p.window,value=owner.metric_choices[key].get());p.metric_variables[key]=variable
            def changed(key=key,variable=variable):
                owner.metric_choices[key].set(variable.get());change_metrics(p)
            toggle=Checkbox(line,variable,changed,p.scale)
            toggle.place(x=p.px(34),y=p.px(10),width=p.px(18),height=p.px(20));p.metric_toggles[key]=toggle
            from product_strip import icon_png
            icon=tk.Label(line,bg=theme.color(BG),bd=0,padx=0,pady=0);icon.art=photo(icon,icon_png(key,owner,p.scale,18));icon.configure(image=icon.art);icon.place(x=p.px(62),y=p.px(11),width=p.px(32),height=p.px(18))
            p.metric_icons[key]=icon
            text(p,line,LABELS[key],13,x=102,y=10,height=20)
            value=p.label(line,'—',12,MUTED,anchor='w');value.place(relx=1,x=-p.px(76),y=p.px(11),width=p.px(72),height=p.px(18));p.live_labels[key]=value;p.metric_rows.append((key,line))
        from metric_sorting import MetricSorter
        def commit(order):owner.metric_order=list(order);p.metric_rows=[(k,dict(p.metric_rows)[k]) for k in order];owner.select_metrics();p.refresh()
        p.metric_sorter=MetricSorter(p,host,p.metric_rows,commit)
        for key,handle in handles.items():p.metric_sorter.bind(key,handle)
        return
    cfg=clean_config(owner.quota_preferences)
    if view=='capsule':
        p.capsule_selectors={};p.capsule_rows=[]
        for key,title in [('capsule_primary','主要数据'),('capsule_secondary','补充数据')]:
            r=row(p,p.body,title,gap=ui.FIELD_GAP if key=='capsule_primary' else 0);p.capsule_rows.append(r)
            def change(value,key=key):
                config=clean_config(owner.quota_preferences);config[key]=value or None;owner.configure_quota(config);p.refresh()
            selector=Select(p,r,metric_choices(p,key,cfg),cfg[key] or '',change);selector.place(relx=1,anchor='ne');p.capsule_selectors[key]=selector
        f=box(p,p.body,ui.HELP_LINE*2+ui.DESCRIPTION_GAP);f.pack_configure(pady=(p.px(ui.HELP_GAP),0));p.capsule_help=f
        text(p,f,'这里的选择不影响展开状态下的指标。',ui.HELP_SIZE,color=MUTED,height=ui.HELP_LINE)
        text(p,f,'点击统计条左侧图标展开或收起。',ui.HELP_SIZE,color=MUTED,y=ui.HELP_LINE+ui.DESCRIPTION_GAP,height=ui.HELP_LINE);return
    f=box(p,p.body,ui.GROUP_TITLE_HEIGHT,ui.GROUP_TITLE_GAP);text(p,f,'统计会话',ui.LABEL_SIZE,True,y=1)
    r=row(p,p.body,'会话选择')
    def binding(mode):
        p.binding_selector.set(owner.binding.mode)
        if mode=='fixed':p.binding_modal=session_dialog(p)
        else:owner.follow_choice.set(True);owner.toggle_follow();p.refresh()
    p.binding_selector=Select(p,r,[('auto','自动跟随'),('fixed','固定会话')],owner.binding.mode,binding);p.binding_selector.place(relx=1,anchor='ne')
    current=Surface(p.body,p.scale,fill='#f1f5fc',padx=0,pady=0,border=False);current.configure(height=p.px(69));current.pack_propagate(False);current.pack(fill='x',pady=(0,p.px(10)))
    p.session_kind=text(p,current.inner,'正在统计',12,color=MUTED,x=14,y=14,height=17,bg=current.fill)
    p.session_current=text(p,current.inner,'',14,True,x=14,y=35,height=22,bg=current.fill)
    p.session_change=p.button(current.inner,'选择会话',lambda:session_dialog(p),quiet=True)
    f=box(p,p.body,ui.HELP_LINE,ui.SECTION_GAP);text(p,f,'用于 Token、TPS、上下文、缓存和轮次。',ui.HELP_SIZE,color=MUTED,height=ui.HELP_LINE)
    f=box(p,p.body,ui.GROUP_TITLE_HEIGHT,ui.GROUP_TITLE_GAP);text(p,f,'账户用量范围',ui.LABEL_SIZE,True,y=1)
    b=p.button(f,'统计说明',lambda:info(p,'统计范围','会话来源只影响会话统计，不切换账户。账户额度由所有会话共享。额度窗口和最近用量范围同时用于展开与收起状态。'),quiet=True);b.place(relx=1,anchor='ne',height=p.px(ui.GROUP_TITLE_HEIGHT))
    group=selected_group(owner.quota_snapshot,cfg);choices=[(w['role'],w['name']) for w in (group or {}).get('windows',[])] or [(cfg['window'],'暂未提供窗口')]
    r=row(p,p.body,'额度窗口');p.scope_selector=Select(p,r,choices,cfg['window'],lambda value:configure(p,'window',value));p.scope_selector.place(relx=1,anchor='ne')
    r=row(p,p.body,'最近用量');p.hours_selector=hours_select(p,r,cfg['hours'],lambda value:configure(p,'hours',value));p.hours_selector.place(relx=1,anchor='ne')
    f=box(p,p.body,18);text(p,f,'展开与收起状态共用此范围；账户用量由所有会话共享。',12,color=MUTED,height=18)

def hours_choices(hours):return [(n,f'最近 {n} 小时') for n in sorted(set((1,3,6,24,hours)))]+[('custom','自定义…')]
def hours_select(p,parent,hours,apply,width=168):
    def choose(value):
        if value=='custom':selector.set(selector.hours);p.range_modal=hours_dialog(p,selector.hours,apply)
        else:selector.hours=value;apply(value)
    selector=Select(p,parent,hours_choices(hours),hours,choose,width=width);selector.hours=hours;return selector

def configure(p,key,value):
    cfg=clean_config(p.owner.quota_preferences);cfg[key]=value;p.owner.configure_quota(cfg);p.refresh()
def change_metrics(p):p.owner.select_metrics();p.refresh()
def select_all(p):
    for choice in p.owner.metric_choices.values():choice.set(True)
    p.owner.select_metrics();p.refresh()
def reset_order(p):p.owner.metric_order=list(METRIC_KEYS);repack_order(p)
def repack_order(p):
    mapping=dict(p.metric_rows)
    p.metric_sorter.sync(p.owner.metric_order)
    p.metric_rows=[(k,mapping[k]) for k in p.owner.metric_order];p.owner.select_metrics();p.refresh()
def reorder(p,moving,target):
    order=list(p.owner.metric_order);order.remove(moving);order.insert(order.index(target),moving);p.owner.metric_order=order;repack_order(p)
def move_order(p,key,delta):
    order=list(p.owner.metric_order);i=order.index(key);j=max(0,min(len(order)-1,i+delta))
    if i!=j:
        order.insert(j,order.pop(i));p.owner.metric_order=order;repack_order(p)
    return 'break'

def build_display(p):
    owner=p.owner;heading(p,'显示方式',action=lambda parent:p.button(parent,'恢复位置',p.reset_position,quiet=True))
    modes=box(p,p.body,72,16);p.mode_buttons={}
    for i,(mode,title,detail) in enumerate([('composer','输入框上方','仅在工作会话显示'),('desktop','桌面悬浮','切换应用也保留')]):
        b=ModeCard(modes,mode,title,detail,lambda mode=mode:p.change_mode(mode),p.scale);b.place(relx=i*.5,x=p.px(6 if i else 0),y=0,relwidth=.5,width=-p.px(6),height=p.px(72));p.mode_buttons[mode]=b
    r=row(p,p.body,'显示统计条',gap=16);p.visibility_choice=tk.BooleanVar(master=p.window,value=getattr(owner,'strip_visible',True));p.switch(r,p.visibility_choice,lambda:set_visible(p)).place(relx=1,rely=.5,anchor='e')
    p.theme_row=row(p,p.body,'主题颜色',gap=16)
    p.theme_button=ThemeSelector(p,p.theme_row,lambda:toggle_theme(p));p.theme_button.place(relx=1,anchor='ne',height=p.px(34),width=p.px(88))
    p.theme_buttons={};p.theme_frame=tk.Frame(p.body,bg=theme.color(BG))
    from settings_panel import ThemeButton
    from color_editor import ColorEditor
    palette=tk.Frame(p.theme_frame,bg=theme.color(BG));palette.pack(fill='x')
    for i,(name,value) in enumerate(theme.PRESETS):
        b=ThemeButton(palette,name,value,lambda value=value:owner.set_theme_color(value),p.scale);b.grid(row=i//4,column=i%4,sticky='ew',padx=(0,p.px(6)) if i%4<3 else 0,pady=(0,p.px(6)));p.theme_buttons[value]=b
    for i in range(4):palette.grid_columnconfigure(i,weight=1,uniform='color')
    p.color_editor=ColorEditor(p.theme_frame,p.scale,theme.current(),owner.set_theme_color,lambda parent,label,cmd,quiet=False:p.button(parent,label,cmd,quiet=quiet),fill=BG);p.color_editor.pack(fill='x',pady=(p.px(2),p.px(4)));p.color_theme_key=theme.current()
    r=row(p,p.body,'统计条大小','文字、图标和高度同步调整。',gap=16);p.font_segments=Segmented(r,((13,'紧凑'),(15,'标准'),(17,'大字')),p.change_font,p.scale,width=160,height=32,font_size=13);p.font_segments.place(relx=1,rely=.5,anchor='e');p.font_buttons=p.font_segments.buttons
    r=row(p,p.body,'平滑过渡','位置和顺序变化时使用平滑动画。',gap=16);p.switch(r,owner.animation_choice,owner.toggle_animations).place(relx=1,rely=.5,anchor='e')
    r=row(p,p.body,'点击穿透','空白处可操作下方应用，数据仍可悬停查看。',gap=0);p.switch(r,owner.lock_choice,owner.toggle_lock).place(relx=1,rely=.5,anchor='e')
    if getattr(p,'theme_open',False):p.theme_frame.pack(fill='x',after=p.theme_row,pady=(0,p.px(16)))

def toggle_theme(p):
    p.theme_open=not getattr(p,'theme_open',False)
    if p.theme_open:p.theme_frame.pack(fill='x',after=p.theme_row,pady=(0,p.px(16)))
    else:p.theme_frame.pack_forget()
    p.refresh()
def set_visible(p):p.owner.strip_visible=p.visibility_choice.get();p.owner.save_preferences()

def refresh(p):
    if p.closed:return
    owner=p.owner;cfg=clean_config(owner.quota_preferences)
    if p.tab=='quota':p.quota_page.refresh();return
    if p.tab=='strip':
        p.view_selector.set(p.strip_view)
        values=metric_values(owner.snapshot,owner.quota_snapshot,cfg)
        for key,label in getattr(p,'live_labels',{}).items():update(label,text=values[key])
        if hasattr(p,'metric_count'):
            for key,variable in p.metric_variables.items():
                actual=bool(owner.metric_choices[key].get())
                if bool(variable.get())!=actual:variable.set(actual)
            update(p.metric_count,text=f'已选 {len(owner.visible_metrics)} 项');update(p.select_all_button,state='disabled' if len(owner.visible_metrics)==len(METRIC_KEYS) else 'normal')
            if p.metric_icon_key!=metric_icon_key(p):
                from product_strip import icon_png
                for key,icon in p.metric_icons.items():icon.art=photo(icon,icon_png(key,owner,p.scale,18));icon.configure(image=icon.art)
                p.metric_icon_key=metric_icon_key(p)
        for key,selector in getattr(p,'capsule_selectors',{}).items():selector.set_choices(metric_choices(p,key,cfg));selector.set(cfg[key] or '')
        if hasattr(p,'session_current'):
            update(p.session_current,text=owner.bound_title or '暂无工作会话');update(p.session_kind,text='正在统计'+(' · 已固定' if owner.binding.mode=='fixed' else ''));p.binding_selector.set(owner.binding.mode)
            p.session_current.place_configure(relwidth=1,width=-p.px(96 if owner.binding.mode=='fixed' else 28))
            if owner.binding.mode=='fixed':p.session_change.place(relx=1,x=-p.px(12),y=p.px(34),anchor='ne',height=p.px(ui.TEXT_ACTION_HEIGHT))
            else:p.session_change.place_forget()
            group=selected_group(owner.quota_snapshot,cfg);choices=[(w['role'],w['name']) for w in (group or {}).get('windows',[])] or [(cfg['window'],'暂未提供窗口')]
            p.scope_selector.set_choices(choices);p.scope_selector.set(cfg['window']);p.hours_selector.set_choices(hours_choices(cfg['hours']));p.hours_selector.hours=cfg['hours'];p.hours_selector.set(cfg['hours'])
    elif p.tab=='display':
        for mode,b in p.mode_buttons.items():b.select(mode==owner.display_mode)
        p.font_segments.select(owner.font_size)
        if p.visibility_choice.get()!=getattr(owner,'strip_visible',True):p.visibility_choice.set(getattr(owner,'strip_visible',True))
        name=next((n for n,c in theme.PRESETS if c==theme.current()),'自定义');update(p.theme_button,text=name,expanded=bool(getattr(p,'theme_open',False)))
        for value,b in p.theme_buttons.items():b.select(value==theme.current())
        if p.color_theme_key!=theme.current():p.color_editor.sync(theme.current(),name);p.color_theme_key=theme.current()

def reset_position(p):p.owner.reset_position()
def install(cls):cls.build_strip=build_strip;cls.build_display=build_display;cls.refresh=refresh;cls.reset_position=reset_position
