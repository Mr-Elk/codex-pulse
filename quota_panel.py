"""Native quota cards and reminder editing, using the existing panel vocabulary."""
import copy
from datetime import datetime
import tkinter as tk
from tkinter import ttk,messagebox

import theme
from panel_widgets import Surface,Segmented,photo
from svg_art import render_asset
from quota_model import clock_text,countdown,selected_group,recent_for_selection
from quota_config import clean_config
from font_policy import family

BG,INK,MUTED,TINT,ACCENT='#ffffff','#1e2238','#6f7691','#f3f1fa','#7865d6'


class Progress(tk.Frame):
    def __init__(self,parent,scale):
        super().__init__(parent,bg=theme.color('#faf9fd'),height=round(8*scale))
        self.scale=scale;self.value=0
        self.back=tk.Label(self,bd=0,bg=theme.color('#faf9fd'));self.back.place(relwidth=1,relheight=1)
        self.front=tk.Label(self,bd=0,bg=theme.color('#faf9fd'));self.front.place(x=0,y=0)
        self.bind('<Configure>',self.draw)

    def draw(self,event=None):
        width,height=self.winfo_width(),self.winfo_height()
        if width<2 or height<2:return
        signature=width,height,self.value,theme.current()
        if signature==getattr(self,'paint_signature',None):return
        self.paint_signature=signature
        self.background=photo(self,render_asset('segment-track.svg',width,height,self.scale,'#eae5f3','#faf9fd'))
        self.back.configure(image=self.background)
        used=round(width*max(0,min(100,self.value))/100)
        if used>1:
            self.foreground=photo(self,render_asset('segment-track.svg',used,height,self.scale,ACCENT,'#faf9fd'))
            self.front.configure(image=self.foreground);self.front.place(x=0,y=0,width=used,height=height)
        else:self.front.place_forget()


class QuotaPanel:
    def __init__(self,panel):
        self.p=panel;self.owner=panel.owner;self.view='overview';self.rows=[];self.signature=None
        p=panel
        self.heading=p.label(p.body,'账户额度',18,bold=True);self.heading.pack(anchor='w')
        self.source=p.label(p.body,'正在连接本机账户…',12,MUTED);self.source.pack(fill='x',pady=p.px(3))
        self.groups=p.button(p.body,'额度组 · 正在读取',self.choose_group)
        self.groups.pack(fill='x',pady=(0,p.px(7)))
        self.navigation=Segmented(p.body,(('overview','概览'),('usage','最近用量'),('credits','重置卡')),self.change_view,p.scale,height=36,font_size=14)
        self.navigation.pack(fill='x',pady=(0,p.px(10)));self.navigation.select('overview')
        self.status=p.label(p.body,'正在读取额度',12,ACCENT,wraplength=p.px(400));self.status.pack(fill='x',pady=(0,p.px(8)))
        self.area=tk.Frame(p.body,bg=theme.color(BG));self.area.pack(fill='x')
        self.meta=p.label(p.body,'',11,MUTED);self.meta.pack(fill='x',pady=(p.px(9),0))
        actions=tk.Frame(p.body,bg=theme.color(BG));actions.pack(fill='x',pady=p.px(5))
        p.button(actions,'刷新',self.request_refresh,quiet=True).pack(side='left')
        self.reminder_button=p.button(actions,'提醒设置',lambda:reminder_dialog(p),quiet=True)
        self.reminder_button.pack(side='right')
        self.message=p.label(p.body,'账户额度独立于会话 Token；窗口之间不相加。',11,MUTED,wraplength=p.px(400))
        self.message.pack(fill='x',pady=p.px(3))
        self.refresh()

    def config(self):return clean_config(getattr(self.owner,'quota_preferences',None))
    def state(self):return getattr(self.owner,'quota_snapshot',{})

    def request_refresh(self):
        service=getattr(self.owner,'quota_service',None)
        if service:service.refresh()
        self.status.configure(text='正在刷新，保留当前布局…')

    def choose_group(self):
        groups=self.state().get('groups') or []
        if len(groups)<2:return
        p=self.p;p.modal_open=True
        popup=tk.Toplevel(p.window);popup.withdraw();popup.transient(p.window);popup.overrideredirect(True);popup.configure(bg=theme.color(BG))
        area=Surface(popup,p.scale,padx=8,pady=8);area.pack(fill='both',expand=True)
        def close():
            p.modal_open=False;popup.grab_release();popup.destroy();p.window.focus_set()
        def select(identity):
            config=self.config();config['group']=identity;close();self.owner.configure_quota(config)
            self.signature=None;self.refresh()
        for group in groups:
            p.button(area.inner,group['name'],lambda identity=group['id']:select(identity),quiet=True).pack(fill='x',pady=p.px(2))
        popup.update_idletasks()
        popup.geometry(f'{max(self.groups.winfo_width(),popup.winfo_reqwidth())}x{popup.winfo_reqheight()}+{self.groups.winfo_rootx()}+{self.groups.winfo_rooty()+self.groups.winfo_height()}')
        popup.bind('<Escape>',lambda _:close());popup.bind('<Button-1>',lambda event:close() if event.widget is popup else None)
        popup.deiconify();popup.lift();popup.grab_set();popup.focus_set()

    def change_view(self,view):
        self.view=view;self.signature=None;self.navigation.select(view);self.refresh()

    def build(self,group,state):
        p=self.p
        for child in self.area.winfo_children():child.destroy()
        self.rows=[]
        if self.view=='overview':
            for role in ('primary','secondary'):
                card=Surface(self.area,p.scale,padx=14,pady=10);card.pack(fill='x',pady=(0,p.px(10)))
                top=tk.Frame(card.inner,bg=theme.color(card.fill));top.pack(fill='x')
                title=p.label(top,'',14,bold=True,bg=card.fill);title.pack(side='left')
                from settings_panel import VectorButton
                focus=VectorButton(top,'关注',lambda r=role:self.focus(r),p.scale,surface_bg=card.fill,height=32,font_size=12);focus.pack(side='right')
                number=p.label(card.inner,'—',29,bold=True,bg=card.fill);number.pack(fill='x',pady=(0,p.px(3)))
                progress=Progress(card.inner,p.scale);progress.pack(fill='x',pady=p.px(3))
                reset=p.label(card.inner,'',12,MUTED,bg=card.fill);reset.pack(fill='x',pady=(p.px(5),0))
                hint=p.label(card.inner,'',11,MUTED,bg=card.fill);hint.pack(fill='x')
                self.rows.append((role,title,focus,number,progress,reset,hint))
        elif self.view=='usage':
            self.range_sync=range_controls(p,self.area)
            cards=tk.Frame(self.area,bg=theme.color(BG));cards.pack(fill='x',pady=(p.px(8),p.px(5)))
            self.usage_cards={}
            from settings_panel import VectorButton
            for index,role in enumerate(('primary','secondary')):
                card=Surface(cards,p.scale,padx=10,pady=9)
                card.grid(row=0,column=index,sticky='nsew',padx=(0,p.px(8)) if index==0 else 0)
                cards.grid_columnconfigure(index,weight=1,uniform='quota')
                button=VectorButton(card.inner,'',lambda role=role:self.focus(role),p.scale,surface_bg=card.fill,height=26,font_size=12)
                button.pack(fill='x')
                number=p.label(card.inner,'等待记录',22,ACCENT,bold=True,bg=card.fill);number.pack(fill='x',pady=p.px(4))
                caption=p.label(card.inner,'',11,MUTED,bg=card.fill);caption.pack(fill='x')
                self.usage_cards[role]=(button,number,caption)
            self.coverage=p.label(self.area,'',12,MUTED,wraplength=p.px(400));self.coverage.pack(fill='x')
            log=Surface(self.area,p.scale,padx=10,pady=8);log.pack(fill='x',pady=p.px(8))
            self.details_title=p.label(log.inner,'',12,MUTED,bg=log.fill);self.details_title.pack(fill='x')
            self.details=p.label(log.inner,'',12,MUTED,bg=log.fill,wraplength=p.px(370),justify='left');self.details.pack(fill='x',pady=p.px(5))
            p.label(self.area,'按各窗口完整额度的百分点估算；未记录区间不补零。',11,MUTED,wraplength=p.px(400),justify='left').pack(fill='x',pady=p.px(4))
            p.button(self.area,'清除本机额度历史',self.clear_history,quiet=True,font_size=12).pack(anchor='w')
        else:
            credits=state.get('credits') or {};count=credits.get('count')
            self.credit_count=p.label(self.area,'',24,bold=True);self.credit_count.pack(fill='x',pady=p.px(5))
            details=credits.get('rows')
            if details is None:p.label(self.area,'服务尚未提供重置卡明细；不会按数量猜过期时间。',12,MUTED,wraplength=p.px(400)).pack(fill='x',pady=p.px(12))
            elif not details:p.label(self.area,'暂无可展示明细',12,MUTED).pack(fill='x',pady=p.px(12))
            for row in (details or []):
                card=Surface(self.area,p.scale,padx=13,pady=10);card.pack(fill='x',pady=(0,p.px(9)))
                p.label(card.inner,row['title'],14,bold=True,bg=card.fill,wraplength=p.px(370),justify='left').pack(fill='x')
                label=p.label(card.inner,'',12,ACCENT,bg=card.fill);label.pack(fill='x',pady=p.px(4))
                expiry=p.label(card.inner,'',11,MUTED,bg=card.fill);expiry.pack(fill='x')
                self.rows.append((row,label,expiry))
            p.label(self.area,'可用数量以服务返回为准，明细可能只返回部分。\n本页只查看状态，使用重置卡请在官方客户端确认。',11,MUTED,wraplength=p.px(400),justify='left').pack(fill='x',pady=p.px(8))

    def focus(self,role):
        config=self.config();config['window']=role;self.owner.configure_quota(config);self.refresh()

    def clear_history(self):
        if messagebox.askyesno('清除本机额度历史','仅清除 Pulse 已积累的额度快照；不会改动账户额度或聊天记录。继续？',parent=self.p.window):
            service=getattr(self.owner,'quota_service',None)
            if service:service.clear_history()

    def refresh(self):
        import time
        state=self.state();config=self.config();group=selected_group(state,config);now=time.time()
        groups=state.get('groups') or [];names=[g['name'] for g in groups]
        self.heading.configure(text={'overview':'账户额度','usage':'最近用量','credits':'重置卡'}.get(self.view,'账户额度'))
        if group:
            self.groups.configure(text='额度组 · '+group['name']+('  ▾' if len(groups)>1 else ''))
        else:self.groups.configure(text='额度组暂不可用')
        if len(groups)>1:
            self.groups.pack(fill='x',before=self.navigation,pady=(0,self.p.px(7)))
        else:self.groups.pack_forget()
        self.source.configure(text=f"{state.get('plan','账户待确认').upper()} · {group['name'] if group else '账户待确认'} · 本机账户额度")
        stale=now-state.get('observed_at',0)>120
        self.status.configure(text='数据已过期 · 请刷新确认' if stale and state.get('status')=='ready' else state.get('message','额度暂不可用'))
        if state.get('status')=='ready' and not stale and state.get('message')=='已同步账户额度':self.status.pack_forget()
        else:self.status.pack(fill='x',before=self.area,pady=(0,self.p.px(8)))
        r=config['reminder']
        self.reminder_button.configure(text=f"提醒 · ≤ {r['threshold']}%" if r['enabled'] else '提醒 · 已关闭')
        credits=state.get('credits') or {}
        sig=(self.view,group['id'] if group else None,
             tuple((r.get('title'),r.get('status'),r.get('expiry')) for r in credits.get('rows') or []) if self.view=='credits' else (),
             credits.get('rows') is None if self.view=='credits' else None)
        if sig!=self.signature:self.signature=sig;self.build(group,state)
        if self.view=='overview':
            windows={w['role']:w for w in group['windows']} if group else {}
            for role,title,focus,number,progress,reset,hint in self.rows:
                w=windows.get(role)
                title.configure(text=w['name'] if w else ('主要窗口' if role=='primary' else '次要窗口'))
                focus.configure(text='已关注' if role==config['window'] else '关注')
                if w:
                    due=w['resets_at'] is not None and now>=w['resets_at']
                    number.configure(text=('上次 ' if due or stale else '剩余 ')+f"{w['remaining']:g}%")
                    progress.value=w['remaining'];progress.draw()
                    reset.configure(text='自然重置 · '+clock_text(w['resets_at']))
                    status='用量受限 · ' if group.get('ordinary_allowed') is False or group.get('reached') else '额度不足 · ' if w['remaining']<=20 else ''
                    hint.configure(text='数据已过期，请刷新确认' if stale else '重置待确认 · 正在等待官方最新额度' if due else status+countdown(w['resets_at'],now))
                else:
                    number.configure(text='—');progress.value=0;progress.draw()
                    reset.configure(text='服务未提供此窗口' if state.get('status')=='ready' else '额度数据暂不可用');hint.configure(text='不按缺失值推断为零')
        elif self.view=='usage':
            self.range_sync()
            windows={w['role']:w for w in (group or {}).get('windows',[])}
            for role,(button,number,caption) in self.usage_cards.items():
                w=windows.get(role);recent=recent_for_selection(state,config,role) or {};spent=recent.get('spent')
                button.configure(text=(w['name'] if w else '窗口暂缺')+'消耗'+(' · 关注' if role==config['window'] else ''))
                number.configure(text='—' if not w else f'≈ {spent:g}' if spent is not None else '等待记录')
                caption.configure(text=('服务未提供此窗口' if state.get('status')=='ready' else '额度数据暂不可用') if not w else
                                  '个百分点'+(' · 部分记录' if recent.get('partial',True) else ' · 采样估算'))
            self.usage=self.usage_cards[config['window']][1]
            recent=recent_for_selection(state,config) or {}
            seconds=recent.get('coverage_seconds',0)
            window=next((w for w in (group or {}).get('windows',[]) if w['role']==config['window']),None)
            self.coverage.configure(text=(window['name']+' · ' if window else '')+f"最近 {config['hours']} 小时 · 已覆盖约 {seconds//60} 分 {seconds%60} 秒"+(' · 部分记录' if recent.get('partial',True) else ' · 采样估算')+('\n'+state['history_error'] if state.get('history_error') else ''))
            self.details_title.configure(text=(window['name'] if window else '所选窗口')+' · 区间记录（点上方卡片切换）')
            lines=[(datetime.fromtimestamp(r['start']).strftime('%H:%M')+'—' if r.get('start') else '')+datetime.fromtimestamp(r['at']).strftime('%H:%M')+'  '+(f"≈ {r['spent']:g} 个百分点" if r['spent'] is not None else '未计入') for r in recent.get('rows',[])]
            self.details.configure(text='\n'.join(lines) or '启用前的历史无法重建；首次读取只建立基线。')
        else:
            count=credits.get('count');self.credit_count.configure(text='可用 '+(f'{count} 张' if count is not None else '—'))
            for row,label,expiry in self.rows:
                label.configure(text='已到期 · 待官方确认' if row['status']=='available' and row['expiry'] and now>=row['expiry'] else row['label'])
                expiry.configure(text='不设到期时间' if row['no_expiry'] else '到期 · '+clock_text(row['expiry'])+(' · '+countdown(row['expiry'],now) if row['expiry'] else ''))
        age=max(0,int(now-state.get('observed_at',now)))
        offset=datetime.now().astimezone().strftime('%z')
        self.meta.configure(text=f"{age} 秒前读取 · UTC{offset[:3]}:{offset[3:]}" if state.get('observed_at') else '时间与额度等待读取')


def range_controls(p,parent):
    owner=p.owner;config=clean_config(getattr(owner,'quota_preferences',None))
    from settings_panel import VectorButton
    header=tk.Frame(parent,bg=theme.color(BG));header.pack(fill='x',pady=(p.px(5),p.px(3)))
    p.label(header,'统计范围',12,MUTED).pack(side='left')
    def choose(hours):
        draft.set(str(hours));seg.select(hours)
        error.pack_forget()
        if hours in (1,3,6,24):row.pack_forget()
        value=clean_config(owner.quota_preferences);value['hours']=hours;owner.configure_quota(value)
    seg=Segmented(parent,tuple((h,f'{h} 小时') for h in (1,3,6,24)),choose,p.scale,height=35,font_size=13)
    seg.pack(fill='x');seg.select(config['hours'])
    row=tk.Frame(parent,bg=theme.color(BG))
    p.label(row,'自定义',12,MUTED).pack(side='left')
    draft=tk.StringVar(master=p.window,value=str(config['hours']))
    entry=tk.Entry(row,textvariable=draft,width=5,font=(family(),-p.px(14)),relief='flat',bg=theme.color(TINT),fg=theme.color(INK))
    entry.pack(side='left',padx=p.px(8),ipady=p.px(4));p.label(row,'小时',12,MUTED).pack(side='left')
    error=p.label(parent,'',11,ACCENT)
    def toggle():
        if row.winfo_manager():row.pack_forget();error.pack_forget()
        else:row.pack(fill='x',after=seg,pady=p.px(5));entry.focus_set()
    custom=VectorButton(header,'自定义小时',toggle,p.scale,quiet=True,height=26,font_size=12)
    custom.pack(side='right')
    def apply():
        try:hours=int(draft.get())
        except ValueError:hours=0
        if not 1<=hours<=168:
            error.configure(text='请输入 1–168 的整数小时');error.pack(fill='x',after=row);return
        error.pack_forget();seg.select(hours);choose(hours)
    VectorButton(row,'应用',apply,p.scale,quiet=True,height=28,font_size=12).pack(side='left',padx=p.px(5))
    entry.bind('<Return>',lambda _:apply())
    def sync():
        current=clean_config(getattr(owner,'quota_preferences',None))['hours']
        seg.select(current)
        custom.configure(text=f'自定义 · {current} 小时' if current not in (1,3,6,24) else '自定义小时')
        if entry.focus_get()!=entry:draft.set(str(current))
    if config['hours'] not in (1,3,6,24):row.pack(fill='x',after=seg,pady=p.px(5))
    sync()
    return sync


def strip_controls(p,parent):
    owner=p.owner
    config=clean_config(getattr(owner,'quota_preferences',None))
    p.rule(parent)
    p.label(parent,'额度关注窗口',12,MUTED).pack(fill='x',pady=(p.px(4),p.px(5)))
    group=selected_group(getattr(owner,'quota_snapshot',{}),config)
    names={w['role']:w['name'] for w in group['windows']} if group else {}
    def choose(key,value):
        prefs=clean_config(getattr(owner,'quota_preferences',None));prefs[key]=value
        owner.configure_quota(prefs)
    window=Segmented(parent,tuple((role,names.get(role,title)) for role,title in (('primary','主要窗口'),('secondary','次要窗口'))),
                     lambda role:choose('window',role),p.scale,height=34,font_size=13)
    window.pack(fill='x');window.select(config['window'])
    range_sync=range_controls(p,parent)
    row=tk.Frame(parent,bg=theme.color(BG));row.pack(fill='x',pady=p.px(6))
    p.label(row,'胶囊摘要',12,MUTED).pack(side='left')
    capsule=Segmented(row,(('quota','账户额度'),('task','会话状态')),lambda value:choose('capsule',value),p.scale,width=220,height=34,font_size=13)
    capsule.pack(side='right');capsule.select(config['capsule'])
    p.label(parent,'额度按账户读取；TPS、Token 等仍按所选工作会话。',11,MUTED).pack(fill='x',pady=p.px(3))
    def sync():
        current=clean_config(getattr(owner,'quota_preferences',None))
        group=selected_group(getattr(owner,'quota_snapshot',{}),current)
        names={w['role']:w['name'] for w in group['windows']} if group else {}
        window.choices=[(role,names.get(role,title)) for role,title in (('primary','主要窗口'),('secondary','次要窗口'))]
        for role,title in window.choices:window.buttons[role].configure(text=title)
        window.select(current['window']);capsule.select(current['capsule']);range_sync()
    return sync


def reminder_dialog(p):
    config=clean_config(getattr(p.owner,'quota_preferences',None));draft=copy.deepcopy(config['reminder'])
    from product_controls import modal,show_modal
    w,frame,close=modal(p,'额度提醒')
    p.label(frame,'选择额度窗口和自己的提醒阈值',12,MUTED).pack(anchor='w',pady=p.px(8))
    enabled=tk.BooleanVar(master=w,value=draft['enabled'])
    row=tk.Frame(frame,bg=theme.color(BG));row.pack(fill='x',pady=p.px(10))
    p.label(row,'低额度提醒',14,bold=True).pack(side='left');p.switch(row,enabled,lambda:None).pack(side='right')
    group=selected_group(getattr(p.owner,'quota_snapshot',{}),config)
    names={r['role']:r['name'] for r in group['windows']} if group else {}
    choices=(('focus','跟随统计条关注窗口'),('primary','主要 · '+names.get('primary','额度窗口')),('secondary','次要 · '+names.get('secondary','额度窗口')),('any','任一窗口，分别判断'))
    source=tk.StringVar(master=w,value=draft['source'])
    p.label(frame,'额度窗口',12,MUTED).pack(anchor='w',pady=(p.px(10),p.px(4)))
    from product_controls import Select
    choices=(('focus','跟随统计条窗口'),('primary',names.get('primary','主要窗口 · 暂未提供')),('secondary',names.get('secondary','次要窗口 · 暂未提供')),('any','任一窗口'))
    sources=Select(p,frame,choices,source.get(),lambda key:source.set(key),width=268)
    sources.pack(anchor='w')
    p.label(frame,'剩余额度低于或等于（%）',12,MUTED).pack(anchor='w',pady=(p.px(14),p.px(5)))
    threshold=tk.StringVar(master=w,value=str(draft['threshold']))
    from product_controls import TextInput
    TextInput(p,frame,threshold,width=88).pack(anchor='w')
    presets=tk.Frame(frame,bg=theme.color(BG));presets.pack(anchor='w',pady=p.px(6))
    for value in (10,20,30):p.button(presets,f'{value}%',lambda n=value:threshold.set(str(n)),quiet=True).pack(side='left',padx=p.px(3))
    info=p.label(frame,'阈值穿越后显示本机浮窗；同一周期与阈值只提醒一次。\n启用后先建立基线；无数据或重置待确认时不提醒。',12,MUTED,wraplength=p.px(330),justify='left');info.pack(fill='x',pady=p.px(9))
    rule=p.label(frame,'',12,ACCENT,wraplength=p.px(330),justify='left');rule.pack(fill='x')
    def preview_rule(*_):
        try:value=int(threshold.get())
        except ValueError:value=-1
        text=(dict(choices)[source.get()]+f'剩余 ≤ {value}% 时提醒') if 0<=value<=100 else '请输入有效阈值'
        rule.configure(text=text if enabled.get() else '提醒已关闭；保存后保留所选窗口和阈值')
    source.trace_add('write',preview_rule);threshold.trace_add('write',preview_rule);enabled.trace_add('write',preview_rule)
    preview_rule()
    error=p.label(frame,'',12,ACCENT);error.pack(fill='x')
    actions=tk.Frame(frame,bg=theme.color(BG));actions.pack(fill='x',pady=(p.px(8),0))
    def save():
        try:value=int(threshold.get())
        except ValueError:value=-1
        if not 0<=value<=100:error.configure(text='请填写 0–100 的整数百分比');return
        config['reminder']={'enabled':enabled.get(),'source':source.get(),'threshold':value}
        p.owner.configure_quota(config);close()
    p.button(actions,'保存',save,dialog=True).pack(side='right');p.button(actions,'取消',close,quiet=True,dialog=True).pack(side='right',padx=(0,p.px(10)))
    show_modal(p,w)
    return w

# Resource hierarchy replaces the former three-tab quota surface.
from product_account import QuotaPanel
