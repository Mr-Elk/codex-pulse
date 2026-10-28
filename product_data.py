"""v19 presentation contract shared by native pages, strip and hover cards."""
from datetime import datetime
import time
from quota_model import selected_group, selected_window, recent_for_selection, clock_text, countdown, quota_percent, used_percent
from quota_config import clean_config, METRIC_KEYS

LABELS={'tokens':'Token','speed':'TPS','context':'上下文估算','cache':'缓存命中率','rounds':'轮次 / 请求',
        'quota':'剩余额度','recent':'最近用量','reset':'自然重置时间','credits':'重置卡数量'}
PRESETS={13:(36,16),15:(40,18),17:(44,20)}

def moment(value):
    if not (isinstance(value, (float, int)) and value > 0):
        return '尚无记录'
    local = datetime.fromtimestamp(value)
    # Python 3.10 on Windows encodes strftime patterns with the system locale.
    return f'{local.month:02d}月{local.day:02d}日 {local.hour:02d}:{local.minute:02d}'

def age(value,now):
    if not isinstance(value,(float,int)):return '尚未读取'
    seconds=max(0,int(now-value))
    return f'{seconds} 秒前' if seconds<60 else f'{seconds//60} 分钟前' if seconds<3600 else f'{seconds//3600} 小时前'

def freshness(state,now=None):
    now=time.time() if now is None else now
    if state.get('status') not in ('ready','stale') or not state.get('account_key'):return 'unavailable'
    return 'stale' if state.get('status')=='stale' or now-(state.get('observed_at') or 0)>120 else 'ready'

def recent_info(state,config,now=None):
    now=time.time() if now is None else now
    config=clean_config(config);group=selected_group(state,config);window=selected_window(state,config)
    record=recent_for_selection(state,config) or {};status=freshness(state,now)
    loading=bool(state.get('history_loading') and not record and not state.get('history_error'))
    known=record.get('spent') is not None and window is not None and status!='unavailable'
    local=('正在读取本机记录' if loading else '暂时无法读取本机记录' if state.get('history_error') else '暂无可计算的用量记录' if not record or record.get('sample_count',0)<2
           else '记录未覆盖全时段' if record.get('partial',True) else '已覆盖所选时段')
    account=('暂未识别账户' if not state.get('account_key') else '暂无额度数据') if status=='unavailable' else (
        ('已过期 · ' if status=='stale' else '已更新 · ')+age(state.get('observed_at'),now))
    notes=[]
    if loading:notes.append('正在读取所选范围的本机记录，读取完成后自动更新。')
    elif state.get('history_error'):notes.append('本机记录暂不可读，账户额度不受影响。')
    elif not record or record.get('sample_count',0)<2:notes.append('首次读取只建立基线，启用前的历史无法重建。')
    elif record.get('partial'):notes.append('仅统计已有记录，未记录的时段不计入。')
    if state.get('status')=='loading':account='正在读取账户额度';notes.append('账户额度读取完成后自动展示。')
    elif status=='stale':notes.append('额度数据已过期，暂按上次额度估算，等待刷新。')
    elif status=='unavailable':notes.append('账户身份或额度未确认，暂不展示旧账号读数；本机历史仍保留。')
    elif window is None:notes.append('账户暂未提供所选额度窗口，无法计算该项用量。')
    return {'source':'根据本机记录估算','value':quota_percent(record['spent']) if known else '—','local':local,'loading':loading,
            'updated':moment(record.get('last_at')),'account':account,'status':status,'notes':notes,
            'window':window,'group':group,'record':record,'hours':config['hours']}

def metric_values(snapshot,quota,config,now=None):
    from overlay_geometry import compact
    now=time.time() if now is None else now;s=snapshot or {};config=clean_config(config)
    available=bool(s.get('available'));display=__import__('quota_model').strip_values(quota,config,now)
    def percent(n):return f'{n:.0f}%' if isinstance(n,(float,int)) else '—'
    return {'tokens':compact(s.get('usage',{}).get('total_tokens')) if available else '—',
        'speed':'生成中' if s.get('request_pending') else f"{s['latest_tps_estimate']:.1f} tok/s" if available and s.get('latest_tps_estimate') is not None else '—',
        'context':percent(s.get('context_percent_estimate')) if available else '—',
        'cache':percent(s.get('cache_hit_percent')) if available else '—',
        'rounds':f"{s.get('rounds','—')}/{s.get('requests','—')}" if available else '—',
        'quota':display['quota'],'recent':recent_info(quota,config,now)['value'],
        'reset':display['reset'],'credits':display['credits']+' 张' if display['credits']!='—' else '—'}

def tooltip(key,snapshot,state,config,session='',now=None):
    now=time.time() if now is None else now;config=clean_config(config)
    values=metric_values(snapshot,state,config,now);window=selected_window(state,config);group=selected_group(state,config)
    scope=(group.get('name','标准额度')+' · '+window['name']) if group and window else '窗口暂未提供'
    result={'title':LABELS[key],'value':values[key],'status':'','rows':[],'body':'','foot':''}
    if key=='recent':
        info=recent_info(state,config,now)
        result.update(title=f"最近 {config['hours']} 小时用量",status='本机估算',
          rows=[('额度口径',scope),('记录范围',f"最近 {config['hours']} 小时"),('本机记录',info['local']),('额度数据',info['account'])],
          body=''.join(['占窗口完整额度的比例；跨越重置时可能超过100%。']+info['notes']),foot='本机记录 · '+info['updated'])
    elif key in ('quota','reset','credits'):
        fresh=freshness(state,now);result['status']='读取中' if state.get('status')=='loading' else {'ready':'账户数据','stale':'数据过期','unavailable':'暂无数据'}[fresh]
        result['foot']='账户数据 · '+age(state.get('observed_at'),now)
        if key=='quota':result.update(rows=[('额度口径',scope),('已用比例',used_percent(window)),('自然重置',countdown(window.get('resets_at'),now) if window else '—')],body='账户共享额度，与会话 Token 分别统计。')
        elif key=='reset':result.update(rows=[('额度窗口',scope),('重置时刻',clock_text(window.get('resets_at')) if window else '—')],body='到期后以账户返回的新额度为准，不自行重置读数。')
        else:
            credits=state.get('credits') or {};rows=credits.get('rows')
            valid=[r for r in rows or [] if r.get('status')=='available' and r.get('expiry') and r['expiry']>now]
            result.update(rows=[('卡片数量',str(credits.get('count','—'))+' 张可用'),('最近到期',clock_text(min(r['expiry'] for r in valid)) if valid else '未提供')],body='可用数量由账户提供，明细可能不包含所有卡片。使用请在官方客户端确认。')
        if state.get('status')=='loading':result.update(value='—',body='正在读取账户额度，读取完成后自动更新。',foot='账户数据 · 正在读取')
    else:
        result['status']='会话统计';result['rows']=[('统计会话',session or '暂无工作会话')]
        result['foot']='会话来源 · '+('累计统计' if key in ('tokens','rounds') else '最近完成请求')
        result['body']={'tokens':'累计输入与输出 Token，包含重复上下文。','speed':'最近完成请求的输出 Token ÷ 请求耗时；是平均估算速度。',
           'cache':'最近完成请求的缓存输入 / 输入 Token。','context':'最近请求上下文占用估算，不是精确剩余 Token。','rounds':'轮次与请求分别累计，一轮可包含多次请求。'}[key]
    return result
