"""Stable account views: update readings in place and retain navigation surfaces."""
import copy,time,sqlite3,tkinter as tk
from concurrent.futures import ThreadPoolExecutor
import theme
import ui_tokens as ui
from quota_records import bucket_minutes,bucket_label,record_range,record_percent,record_status
from panel_widgets import Surface,photo
from panel_runtime import Number,update
from product_panel import box,text,hours_select,hours_choices
from product_controls import Select,info,OutlineButton
from product_data import recent_info,freshness,moment,age
from quota_model import selected_group,selected_window,clock_text,countdown,quota_percent,used_percent,balance_text
from quota_service import clean_config
BG,INK,MUTED,ACCENT='#ffffff','#233955','#607088','#7865d6'

class QuotaPanel:
    def __init__(self,p):
        self.p=p;self.owner=p.owner;self.host=p.body;self.view='overview';self.views={};self.widgets={};self.rows=[];self.expanded=False;self.history_open={}
        self.analysis_config=self.config();self.executor=None;self.future=None;self.future_key=None;self.query_key=None;self.query_cache={};self.query_job=None;self.query_error=None
        self.show('overview');self.refresh()
    def config(self):return clean_config(self.owner.quota_preferences)
    def state(self):
        state=getattr(self.owner,'quota_snapshot',{})
        return {**state,'groups':[],'credits':None} if freshness(state)=='unavailable' else state
    def frame(self,parent):return tk.Frame(parent,bg=theme.color(BG))
    def show(self,view):
        if view not in self.views:
            frame=self.frame(self.host);self.views[view]={'frame':frame,'widgets':{},'rows':[]}
            self.body=frame;self.widgets=self.views[view]['widgets'];self.rows=self.views[view]['rows']
            if view=='overview':self.build_overview()
            elif view=='usage':self.build_usage()
            else:self.build_credits()
        data=self.views[view]
        # The old page stays mapped while its destination is being built.
        data['frame'].pack(fill='x')
        for name,entry in self.views.items():
            if name!=view:entry['frame'].pack_forget()
        self.view=view;self.body=data['frame'];self.widgets=data['widgets'];self.rows=data['rows']
    def change_view(self,view):
        origin=self.view
        if view=='usage' and origin!='usage':self.analysis_config=copy.deepcopy(self.config());self.expanded=False
        self.show(view);self.refresh();self.p.content.yview_moveto(0)
        if view=='overview':
            target=self.widgets.get('usage_entry' if origin=='usage' else 'credits_entry')
            if target:self.p.window.after_idle(target.focus_set)
    def title(self,value,back=False):
        p=self.p;f=box(p,self.body,36 if back else 48,20 if back else 9)
        text(p,f,value,17,True,y=5 if back else 0,height=26)
        if back:
            b=OutlineButton(p,f,'返回账户',lambda:self.change_view('overview'));b.place(relx=1,anchor='ne',y=p.px(2));self.widgets['back']=b
        else:
            text(p,f,'ChatGPT 账户 · 所有会话共享',12,color=MUTED,y=30,height=18)
            from settings_panel import IconButton
            b=IconButton(f,self.request_refresh,p.scale);b.place(relx=1,anchor='ne',y=0,width=p.px(ui.ICON_ACTION_SIZE),height=p.px(ui.ICON_ACTION_SIZE));self.widgets['refresh_button']=b
    def request_refresh(self):
        service=getattr(self.owner,'quota_service',None)
        if service:service.refresh()
        if 'status' in self.widgets:update(self.widgets['status'],text='正在刷新账户数据…')
    def reminder(self):
        from quota_panel import reminder_dialog
        return reminder_dialog(self.p)
    def build_overview(self):
        p=self.p;w=self.widgets;self.title('账户资源')
        f=box(p,self.body,18,24);w['status']=text(p,f,'',12,color=MUTED,height=18)
        w['group_host']=self.frame(self.body)
        f=box(p,self.body,24,12);w['section_heading']=f;text(p,f,'标准额度',14,True,y=1)
        w['usage_entry']=p.button(f,'最近用量 ›',lambda:self.change_view('usage'),quiet=True);w['usage_entry'].place(relx=1,anchor='ne')
        w['windows']=self.frame(self.body);w['windows'].configure(height=p.px(159));w['windows'].pack(fill='x');w['windows'].pack_propagate(False)
        w['windows'].grid_columnconfigure(0,weight=1,uniform='account');w['windows'].grid_columnconfigure(1,weight=1,uniform='account');w['cards']={}
        f=box(p,self.body,24,24);f.pack_configure(pady=(p.px(10),p.px(24)));w['reminder']=text(p,f,'',12,color=MUTED,y=6,height=18)
        b=p.button(f,'设置提醒',self.reminder,quiet=True);b.place(relx=1,anchor='ne')
        f=box(p,self.body,44,24);w['balance_host']=f;w['balance_layout']=None;text(p,f,'额外余额',14,True);w['balance_note']=text(p,f,'',12,color=MUTED,y=26,height=18)
        w['balance']=p.label(f,'—',24,bold=True,anchor='e');w['balance'].place(relx=1,anchor='ne',y=p.px(6),height=p.px(32),width=p.px(140))
        entry=Surface(self.body,p.scale,fill='#f1f5fc',padx=0,pady=0);entry.configure(height=p.px(73),takefocus=True,cursor='hand2');entry.pack_propagate(False);entry.pack(fill='x');w['credits_entry']=entry
        from product_strip import icon_png
        icon=tk.Label(entry.inner,bg=theme.color(entry.fill),bd=0);icon.art=photo(icon,icon_png('credits',self.owner,p.scale,20));icon.configure(image=icon.art);icon.place(x=p.px(15),y=p.px(25),width=p.px(24),height=p.px(24))
        text(p,entry.inner,'重置卡',14,True,x=51,y=15,bg=entry.fill);w['credits_hint']=text(p,entry.inner,'',12,color=MUTED,x=51,y=40,height=18,bg=entry.fill)
        w['credits_count']=p.label(entry.inner,'—',13,ACCENT,bg=entry.fill,anchor='e');w['credits_count'].place(relx=1,x=-p.px(32),anchor='ne',y=p.px(27),height=p.px(19),width=p.px(100))
        arrow=text(p,entry.inner,'›',18,color=MUTED,y=23,height=24,bg=entry.fill);arrow.place(relx=1,x=-p.px(14),anchor='ne',y=p.px(23),width=p.px(12),height=p.px(24))
        def bind(widget):
            widget.bind('<Button-1>',lambda _:self.change_view('credits'));widget.configure(cursor='hand2')
            for child in widget.winfo_children():bind(child)
        bind(entry);entry.bind('<Return>',lambda _:self.change_view('credits'));entry.invoke=lambda:self.change_view('credits')
    def update_windows(self,group,status,now):
        from quota_panel import Progress
        p=self.p;w=self.widgets;host=w['windows'];cards=w['cards'];windows=(group or {}).get('windows',[]);keys={item['role'] for item in windows}
        for key in list(cards):
            if key not in keys:cards.pop(key)['surface'].destroy()
        if not windows:
            if 'empty' not in cards:
                label=p.label(host,'',13,MUTED,wraplength=p.px(385),justify='left');label.pack(anchor='w',pady=p.px(14));cards['empty']={'surface':label}
            update(cards['empty']['surface'],text='正在读取账户额度…' if self.state().get('status')=='loading' else '账户暂未提供额度信息。')
            host.configure(height=p.px(72));self.rows=[];return
        if 'empty' in cards:cards.pop('empty')['surface'].destroy()
        host.configure(height=p.px(159))
        for i,item in enumerate(windows):
            role=item['role']
            if role not in cards:
                s=Surface(host,p.scale,fill='#f8fbff',padx=0,pady=0);s.configure(height=p.px(159));s.pack_propagate(False)
                title=text(p,s.inner,item['name'],14,True,x=15,y=13,bg=s.fill)
                number=Number(p,s.inner,size=28,height=40,bg=s.fill);number.place(x=p.px(15),y=p.px(43),relwidth=1,width=-p.px(30),height=p.px(40))
                label=text(p,s.inner,'剩余',12,color=MUTED,x=90,y=58,height=18,bg=s.fill)
                progress=Progress(s.inner,p.scale);progress.place(x=p.px(15),y=p.px(93),relwidth=1,width=-p.px(30),height=p.px(4))
                used=text(p,s.inner,'',12,color=MUTED,x=15,y=106,height=18,bg=s.fill);reset=text(p,s.inner,'',12,color=MUTED,x=15,y=128,height=18,bg=s.fill)
                cards[role]={'surface':s,'title':title,'number':number,'remaining':label,'progress':progress,'used':used,'reset':reset}
            c=cards[role];single=len(windows)==1
            c['surface'].grid(row=0,column=i,columnspan=2 if single else 1,sticky='nsew',padx=0 if single else (0,p.px(6)) if i==0 else (p.px(6),0))
            update(c['title'],text=item['name']);c['number'].set(quota_percent(item['remaining']))
            import tkinter.font as font
            end=font.Font(root=c['number'].main,font=c['number'].main.cget('font')).measure(quota_percent(item['remaining'],False))+font.Font(root=c['number'].unit,font=c['number'].unit.cget('font')).measure('%')+p.px(8)
            c['remaining'].place_configure(x=p.px(15)+end)
            if c['progress'].value!=item['remaining']:c['progress'].value=item['remaining'];c['progress'].draw()
            update(c['used'],text='已使用 '+used_percent(item)+(' · 上次读数' if status=='stale' else ''))
            update(c['reset'],text='重置待确认' if item['reset_pending'] else countdown(item['resets_at'],now)+'重置')
        self.rows=[(k,c['number'],c['progress'],c['used'],c['reset']) for k,c in cards.items()]
        self.views['overview']['rows']=self.rows
    def scoped_state(self,state):
        scoped=copy.deepcopy(state);cfg=self.analysis_config;window=selected_window(scoped,cfg);service=getattr(self.owner,'quota_service',None)
        if not window or freshness(state)=='unavailable' or not service or not service.history:return scoped
        scope=(state.get('account_key'),window['key'],window['basis'],cfg['hours'])
        if self.query_error==scope:scoped['history_error']='本机历史读取失败，请稍后重试'
        record=self.query_cache.get(scope)
        if record:scoped['recent_by_window']={window['key']:record};scoped['recent']=record
        key=(*scope,state.get('observed_at'))
        if key!=self.query_key and self.future is None:
            if self.executor is None:self.executor=ThreadPoolExecutor(max_workers=1,thread_name_prefix='pulse-details')
            self.query_key=key;self.future_key=scope;self.future=self.executor.submit(service.history.recent,state['account_key'],copy.deepcopy(window),cfg['hours'],time.time())
            self.query_job=self.p.window.after(30,self.check_query)
        from quota_model import recent_for_selection
        if self.future is not None and self.future_key==scope and not recent_for_selection(scoped,cfg):scoped['history_loading']=True
        return scoped
    def check_query(self):
        self.query_job=None
        if self.p.closed:return
        if self.future and not self.future.done():self.query_job=self.p.window.after(30,self.check_query);return
        try:
            if self.future:self.query_cache[self.future_key]=self.future.result();self.query_error=None
        except (OSError,sqlite3.Error):self.query_error=self.future_key
        self.future=None
        if self.view=='usage':self.refresh()
    def change_analysis(self,key,value):self.analysis_config[key]=value;self.expanded=False;self.refresh()
    def toggle_records(self):self.expanded=not self.expanded;self.refresh()
    def build_usage(self):
        p=self.p;w=self.widgets;self.title('最近用量',True)
        s=Surface(self.body,p.scale,fill='#f8fbff',padx=0,pady=0);s.configure(height=p.px(248));s.pack_propagate(False);s.pack(fill='x');w['card']=s
        filters=tk.Frame(s.inner,bg=theme.color(s.fill));filters.place(x=p.px(17),y=p.px(17),relwidth=1,width=-p.px(34),height=p.px(34))
        cfg=self.analysis_config;group=selected_group(self.state(),cfg);choices=[(x['role'],x['name']) for x in (group or {}).get('windows',[])] or [(cfg['window'],'窗口暂未提供')]
        w['window']=Select(p,filters,choices,cfg['window'],lambda v:self.change_analysis('window',v),width=128);w['window'].place(x=0,y=0)
        w['hours']=hours_select(p,filters,cfg['hours'],lambda v:self.change_analysis('hours',v),width=144);w['hours'].place(x=p.px(136),y=0)
        text(p,s.inner,'根据本机记录估算',12,color=ACCENT,x=17,y=78,height=18,bg=s.fill)
        b=p.button(s.inner,'计算说明',lambda:info(p,'最近用量计算','根据本机保存的额度变化估算用量，未记录时段不计入。跨越已确认的额度重置时，累计用量可能超过 100%。本机记录与账户数据分别显示更新状态。此处筛选仅影响本页。'),quiet=True);b.place(relx=1,x=-p.px(17),anchor='ne',y=p.px(75))
        w['usage']=Number(p,s.inner,size=32,height=40,unit_size=18,bg=s.fill);w['usage'].place(x=p.px(17),y=p.px(105),relwidth=1,width=-p.px(34),height=p.px(40))
        w['basis']=text(p,s.inner,'',12,color=MUTED,x=17,y=153,height=18,bg=s.fill)
        for key,title,y in [('local','本机记录',187),('account','额度数据',213)]:
            text(p,s.inner,title,12,color=MUTED,x=17,y=y,height=18,bg=s.fill)
            w[key]=text(p,s.inner,'',12,color=MUTED,x=81,y=y,height=18,bg=s.fill)
        w['notice']=p.label(s.inner,'',12,MUTED,bg=s.fill,wraplength=p.px(385),justify='left')
        f=box(p,self.body,36);f.pack_configure(pady=(p.px(20),0));w['records_toggle']=p.button(f,'查看区间记录',self.toggle_records,quiet=True,align='w');w['records_toggle'].place(x=0,y=0,height=p.px(36),width=p.px(100))
        w['records_arrow']=p.button(f,'⌄',self.toggle_records,kind='icon',font_size=14,tab_stop=False);w['records_arrow'].place(relx=1,anchor='ne',height=p.px(36),width=p.px(32))
        w['records']=self.frame(self.body);w['record_rows']={};w['record_scope']=p.label(w['records'],'',ui.HELP_SIZE,MUTED);w['record_scope'].pack(fill='x',pady=(p.px(ui.HELP_GAP),p.px(ui.FIELD_GAP)))
    def update_records(self,data):
        p=self.p;w=self.widgets;host=w['records'];rows=w['record_rows']
        update(w['records_toggle'],text=('收起' if self.expanded else '查看')+'区间记录');update(w['records_arrow'],text='⌃' if self.expanded else '⌄')
        if not self.expanded:host.pack_forget();return
        host.pack(fill='x');minutes=data['record'].get('bucket_minutes',bucket_minutes(self.analysis_config['hours']));update(w['record_scope'],text=f"每 {bucket_label(minutes)}汇总 · 本地时间")
        records=data['record'].get('rows',[])
        if not records:records=[{'at':None,'start':None,'spent':None}]
        keys=set()
        for index,item in enumerate(records):
            key=item.get('key',(item.get('start'),item.get('at')));keys.add(key)
            if key not in rows:
                f=box(p,host,ui.RECORD_HEIGHT,ui.RECORD_GAP);a=text(p,f,'',ui.CONTROL_SIZE,y=3,height=ui.CONTROL_LINE);a.place_configure(relwidth=1,width=-p.px(60));b=p.label(f,'',ui.LABEL_SIZE,INK,bold=True,anchor='e');b.place(relx=1,anchor='ne',y=p.px(2),height=p.px(ui.LABEL_LINE),width=p.px(56));c=text(p,f,'',ui.HELP_SIZE,color=MUTED,y=28,height=ui.HELP_LINE);rows[key]=(f,a,b,c)
            f,a,b,c=rows[key]
            f.pack_configure(after=w['record_scope'] if index==0 else rows[previous][0]);previous=key
            empty=item.get('start') is None or item.get('at') is None
            update(a,text=('正在读取区间记录…' if data.get('loading') else '尚无可估算区间') if empty else record_range(item));update(b,text='' if empty else record_percent(item.get('spent')))
            status='启用前的历史无法重建。' if empty else record_status(item)
            update(c,text=status);update(f,height=p.px(ui.RECORD_HEIGHT if status else ui.CONTROL_HEIGHT))
            a.place_configure(y=p.px(3 if status else (ui.CONTROL_HEIGHT-ui.CONTROL_LINE)//2));b.place_configure(y=p.px(2 if status else (ui.CONTROL_HEIGHT-ui.LABEL_LINE)//2))
            if status:c.place_configure(y=p.px(28),height=p.px(ui.HELP_LINE))
            else:c.place_forget()
        for key in set(rows)-keys:rows.pop(key)[0].destroy()
    def build_credits(self):
        p=self.p;w=self.widgets;self.title('重置卡',True)
        f=box(p,self.body,36,20);w['count']=Number(p,f,size=28,height=36,unit_size=14,bg=BG);w['count'].place(x=0,y=0,width=p.px(180),height=p.px(36))
        w['expiring']=p.label(f,'',12,MUTED,anchor='e');w['expiring'].place(relx=1,anchor='ne',y=p.px(16),height=p.px(18))
        w['cards_host']=self.frame(self.body);w['cards_host'].pack(fill='x');w['cards']={}
        w['used_toggle']=p.button(self.body,'',lambda:self.toggle_history('used'),quiet=True,align='w')
        w['used_host']=self.frame(self.body);w['used_cards']={}
        w['cards_help']=p.label(self.body,'使用请在官方客户端确认。',12,MUTED);w['cards_help'].pack(fill='x',pady=(p.px(22),0))
    def toggle_history(self,key):self.history_open[key]=not self.history_open.get(key,False);self.refresh()
    def sync_cards(self,host,mapping,items):
        p=self.p;keys=[]
        for index,item in enumerate(items):
            key=(item.get('granted_at'),item.get('expiry'),item.get('status'),index);keys.append(key)
            if key not in mapping:
                s=Surface(host,p.scale,fill='#fffbf3' if item.get('label')=='即将到期' else '#f8fbff',padx=0,pady=0);s.configure(height=p.px(76));s.pack_propagate(False);s.pack(fill='x',pady=(0,p.px(12)))
                title=text(p,s.inner,'',14,True,x=17,y=15,bg=s.fill);expiry=text(p,s.inner,'',12,color=MUTED,x=17,y=43,height=18,bg=s.fill)
                status=Surface(s.inner,p.scale,fill='#fff0d5' if item.get('label')=='即将到期' else '#f1f5fc',padx=7,pady=1,border=False);status.place(relx=1,x=-p.px(17),anchor='ne',y=p.px(15),height=p.px(22));label=p.label(status.inner,'',12,'#926015' if item.get('label')=='即将到期' else ACCENT,bg=status.fill);label.pack()
                mapping[key]=(s,title,expiry,label)
            s,title,expiry,label=mapping[key]
            name=item.get('title');name=f'重置卡 {index+1:02}' if not name or name=='额度重置卡' else name
            update(title,text=name);update(label,text=item.get('label','状态待确认'));update(expiry,text='未提供使用时间' if item.get('status')=='redeemed' else '不设到期时间' if item.get('no_expiry') else clock_text(item.get('expiry'))+' 到期' if item.get('expiry') else '未提供到期时间')
        for key in set(mapping)-set(keys):mapping.pop(key)[0].destroy()
    def refresh(self):
        if self.p.closed:return
        p=self.p
        state=self.state();cfg=self.config();now=time.time();group=selected_group(state,self.analysis_config if self.view=='usage' else cfg);w=self.widgets;status=freshness(state,now)
        if self.view=='overview':
            update(w['status'],text=('已连接 · '+age(state.get('observed_at'),now)+'更新') if status=='ready' else ('额度数据过期 · '+age(state.get('observed_at'),now)) if status=='stale' else state.get('message','账户身份待确认'))
            groups=state.get('groups') or []
            if len(groups)>1:
                host=w['group_host'];host.pack(fill='x',before=w['section_heading'],pady=(0,self.p.px(18)))
                if 'group_selector' not in w:
                    def choose(identity):
                        config=self.config();config['group']=identity;self.owner.configure_quota(config);self.refresh()
                    w['group_selector']=Select(self.p,host,[],None,choose);w['group_selector'].pack(anchor='w')
                w['group_selector'].set_choices([(g['id'],g['name']) for g in groups]);w['group_selector'].set(group['id'])
            else:w['group_host'].pack_forget()
            self.update_windows(group,status,now);rule=cfg['reminder'];update(w['reminder'],text=f"剩余 ≤ {rule['threshold']}% 时提醒" if rule['enabled'] else '提醒未开启。')
            balance=(group or {}).get('balance') or {};update(w['balance'],text='不限额' if balance.get('unlimited') else balance_text(balance.get('value')));update(w['balance_note'],text='余额单位暂未提供' if balance.get('value') is not None else '账户暂未提供余额')
            import tkinter.font as font
            long_balance=font.Font(root=w['balance'],font=w['balance'].cget('font')).measure(w['balance'].cget('text'))>p.px(140)
            if long_balance!=w['balance_layout']:
                w['balance_layout']=long_balance;w['balance_host'].configure(height=p.px(84 if long_balance else 44))
                w['balance_note'].place_configure(y=p.px(64 if long_balance else 26))
                w['balance'].place_forget();w['balance'].configure(anchor='w' if long_balance else 'e')
                if long_balance:w['balance'].place(x=0,y=p.px(25),height=p.px(32),relwidth=1)
                else:w['balance'].place(relx=1,anchor='ne',y=p.px(6),height=p.px(32),width=p.px(140))
            credits=state.get('credits') or {};count=credits.get('count');update(w['credits_count'],text=f'{count} 张可用' if count is not None else '数量待确认')
            expiring=sum(1 for c in credits.get('rows') or [] if c.get('label')=='即将到期');update(w['credits_hint'],text=f'{expiring} 张即将到期' if expiring else '上次记录' if status=='stale' else '查看有效期与使用记录')
        elif self.view=='usage':
            choices=[(x['role'],x['name']) for x in (group or {}).get('windows',[])] or [(self.analysis_config['window'],'窗口暂未提供')];w['window'].set_choices(choices);w['window'].set(self.analysis_config['window']);w['hours'].hours=self.analysis_config['hours'];w['hours'].set_choices(hours_choices(self.analysis_config['hours']));w['hours'].set(self.analysis_config['hours'])
            data=recent_info(self.scoped_state(state),self.analysis_config,now);w['usage'].set(data['value']);name=(data['window'] or {}).get('name','所选窗口').replace('额度','');update(w['basis'],text='占'+name+'完整额度的消耗比例')
            update(w['local'],text='正在读取所选时间范围…' if data.get('loading') else data['local']+(' · '+data['updated']+' 更新' if data['record'].get('last_at') else ''));update(w['account'],text=data['account'],fg=theme.color(MUTED) if data['status']=='ready' else '#91601f')
            note=' '.join(data['notes']);update(w['notice'],text=note)
            if note:
                height=w['notice'].winfo_reqheight()
                w['notice'].place(x=self.p.px(17),y=self.p.px(239),relwidth=1,width=-self.p.px(34),height=height);update(w['card'],height=self.p.px(256)+height)
            else:w['notice'].place_forget();w['card'].configure(height=self.p.px(248))
            self.update_records(data)
        else:
            credits=state.get('credits') or {};count=credits.get('count');w['count'].set(count if count is not None else '—','张可用' if count is not None else '')
            rows=credits.get('rows');available=sorted([r for r in rows or [] if r.get('status')!='redeemed'],key=lambda r:r.get('expiry') or float('inf'));self.sync_cards(w['cards_host'],w['cards'],available)
            expiring=sum(1 for x in available if x.get('label')=='即将到期');update(w['expiring'],text=f'{expiring} 张即将到期' if expiring else '上次记录' if status=='stale' else '')
            used=[r for r in rows or [] if r.get('status')=='redeemed']
            if used:
                update(w['used_toggle'],text=('⌃' if self.history_open.get('used') else '›')+f' 已使用 · {len(used)} 张');w['used_toggle'].pack(fill='x',before=w['cards_help'],pady=(self.p.px(6),0))
                if self.history_open.get('used'):w['used_host'].pack(fill='x',before=w['cards_help']);self.sync_cards(w['used_host'],w['used_cards'],used)
                else:w['used_host'].pack_forget()
            else:w['used_toggle'].pack_forget();w['used_host'].pack_forget()
            update(w['cards_help'],text='正在读取重置卡…' if state.get('status')=='loading' else ('账户仅提供可用数量，暂未提供卡片明细。\n' if rows is None else '暂无可显示的卡片明细。\n' if not rows else '')+'使用请在官方客户端确认。')
    def close(self):
        if self.query_job:
            try:self.p.window.after_cancel(self.query_job)
            except tk.TclError:pass
            self.query_job=None
        if self.executor:self.executor.shutdown(wait=False,cancel_futures=True)
