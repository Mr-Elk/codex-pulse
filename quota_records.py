"""Readable interval summaries; never interpolate or turn missing data into zero."""
from datetime import datetime,timedelta,timezone
from decimal import Decimal,ROUND_HALF_UP

def bucket_minutes(hours):
    for upper,minutes in ((2,15),(6,30),(12,60),(24,180),(72,360),(168,1440)):
        if hours<=upper:return minutes
    return 1440

def bucket_label(minutes):
    return f'{minutes//60} 小时' if minutes%60==0 else f'{minutes} 分钟'

def bucket_bounds(at,minutes):
    # Local wall-clock boundaries; constructing the next date also handles
    # 23/25-hour local days without assuming a day is always 86400 seconds.
    local=datetime.fromtimestamp(at,timezone.utc).astimezone()
    offset=(local.hour*60+local.minute)//minutes*minutes
    start=local.replace(hour=offset//60,minute=offset%60,second=0,microsecond=0)
    end=start+timedelta(minutes=minutes)
    left,right=start.timestamp(),end.timestamp()
    offset_at_end=datetime.fromtimestamp(right,timezone.utc).astimezone().utcoffset()
    right+=(local.utcoffset()-offset_at_end).total_seconds()
    return left,right if right>left else left+minutes*60

def aggregate_records(details,hours,now):
    """Group all eligible deltas, keeping whole sampling pairs at boundaries.

    A pair belongs to its ending clock bucket. Display its actual sampling
    start/end, not a fabricated fully covered bucket. Invalid pairs remain
    visible as missing. No prorating across gaps or reset boundaries occurs.
    """
    minutes=bucket_minutes(hours);cutoff=now-hours*3600;groups={}
    for item in details:
        end=item.get('at');start=item.get('start')
        if not isinstance(start,(int,float)) or not isinstance(end,(int,float)) or end<=start or end<=cutoff or end>now:continue
        left,right=bucket_bounds(end-0.000001,minutes)
        group=groups.setdefault(left,{'key':left,'bucket_end':right,'start':max(start,cutoff),'at':end,'spent':None,'coverage_seconds':0.,'notes':[],'sample_count':0,'valid_count':0})
        group['start']=min(group['start'],max(start,cutoff));group['at']=max(group['at'],end);group['sample_count']+=1
        spent=item.get('spent');note=item.get('note','')
        if spent is not None:
            group['spent']=(group['spent'] or 0.)+spent;group['valid_count']+=1
            if not note:group['coverage_seconds']+=max(0,end-max(start,cutoff))
        if note and note not in group['notes']:group['notes'].append(note)
    result=[]
    for key,group in sorted(groups.items()):
        expected=max(0,min(group['bucket_end'],now)-max(key,cutoff))
        group['partial']=group['coverage_seconds']<expected*.98 or bool(group['notes'])
        if group['spent'] is not None:group['spent']=round(group['spent'],8)
        result.append(group)
    return result

def record_range(item):
    a,b=datetime.fromtimestamp(item['start']),datetime.fromtimestamp(item['at'])
    if a.date()!=b.date():return a.strftime('%m月%d日 %H:%M')+' – '+b.strftime('%m月%d日 %H:%M')
    pattern='%H:%M:%S' if a.strftime('%H:%M')==b.strftime('%H:%M') else '%H:%M'
    return a.strftime('%m月%d日 ')+a.strftime(pattern)+' – '+b.strftime(pattern)

def record_percent(value):
    if value is None:return '—'
    if 0<value<1:return '<1%'
    return str(Decimal(str(value)).quantize(Decimal('1'),rounding=ROUND_HALF_UP))+'%'

def record_status(item):
    if item['spent'] is None:return '记录中断或口径未确认，未计入'
    if item.get('notes'):return '部分记录 · 含未计入区间或重置边界'
    return '部分记录 · 仅汇总已记录消耗' if item.get('partial') else ''
