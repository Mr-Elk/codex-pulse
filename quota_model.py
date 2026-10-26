"""Portable quota presentation. Official values, local time, explicit missingness."""
from datetime import datetime, timezone
import hashlib
import math
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


def number(value):
    return isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value)


def quota_percent(value, suffix=True):
    """Integer presentation only; account/history calculations keep full precision."""
    if not number(value):return '—'
    try:digits=str(Decimal(str(value)).quantize(Decimal('1'),rounding=ROUND_HALF_UP))
    except InvalidOperation:return '—'
    return digits+('%' if suffix else '')


def balance_text(value):
    """Round only the visible balance, retaining the exact source for data use."""
    if value is None or isinstance(value,bool):return '—'
    try:
        amount=Decimal(str(value))
        if not amount.is_finite():return '—'
        return format(amount.to_integral_value(rounding=ROUND_HALF_UP),',f')
    except (InvalidOperation,ValueError):return '—'


def used_percent(window):
    # Keep complementary displayed readings consistent at the half-point edge.
    if not window:return '—'
    used=window.get('used')
    if number(used) and 0<=used<=100 and number(window.get('remaining')):
        return str(100-int(quota_percent(window['remaining'],False)))+'%'
    return quota_percent(used)


def timestamp(value):
    return value if number(value) and 0 < value < 253402300799 else None


def window_name(minutes):
    if not number(minutes) or minutes<=0:return "额度窗口"
    if minutes%1440==0:return f"{minutes//1440:g} 天额度"
    if minutes%60==0:return f"{minutes//60:g} 小时额度"
    return f"{minutes:g} 分钟额度"


def clock_text(value):
    if timestamp(value) is None:return "暂未提供"
    return datetime.fromtimestamp(value,timezone.utc).astimezone().strftime("%m 月 %d 日 %H:%M")


def countdown(value,now):
    if timestamp(value) is None:return "时间暂未提供"
    seconds=max(0,int(value-now))
    if seconds==0:return "等待官方确认"
    if seconds<60:return "不足 1 分钟"
    minutes=seconds//60;days,minutes=divmod(minutes,1440);hours,minutes=divmod(minutes,60)
    return (f"{days} 天 " if days else "")+(f"{hours} 小时 " if hours else "")+f"{minutes} 分钟后"


def normalize(result,now):
    account=result.get("account_id")
    if not isinstance(account,str) or not account.strip():
        return {"status":"unavailable","message":"服务未提供稳定账户标识，暂不展示或积累额度","observed_at":now,"groups":[],"credits":None}
    account_key=hashlib.sha256(account.encode()).hexdigest()
    limits=result.get("limits") or {};raw=limits.get("rateLimitsByLimitId")
    if not isinstance(raw,dict) or not raw:
        legacy=limits.get("rateLimits")
        raw={str(legacy.get("limitId") or "default"):legacy} if isinstance(legacy,dict) else {}
    groups=[]
    for key,item in raw.items():
        if not isinstance(item,dict):continue
        windows=[]
        for role in ("primary","secondary"):
            w=item.get(role)
            if not isinstance(w,dict) or not number(w.get("usedPercent")) or w["usedPercent"]<0:continue
            duration=w.get("windowDurationMins");duration=duration if number(duration) and duration>0 else None
            reset=timestamp(w.get("resetsAt"));used=float(w["usedPercent"])
            basis=f"{result.get('plan')}|{duration}|{item.get('normalModelSlug')}"
            windows.append({"key":f"{key}:{role}","role":role,"minutes":duration,"name":window_name(duration),
                "used":used,"remaining":max(0,min(100,100-used)),"resets_at":reset,
                "reset_pending":reset is not None and now>=reset,"basis":basis})
        name=item.get("limitName") or key
        credit=item.get('credits');balance=None
        if isinstance(credit,dict):
            raw_balance=credit.get('balance');amount=None
            try:
                parsed=Decimal(raw_balance) if isinstance(raw_balance,str) else None
                if parsed is not None and parsed.is_finite() and parsed>=0:amount=format(parsed,'f')
            except InvalidOperation:pass
            balance={'value':amount,'has_credits':credit.get('hasCredits') is True,'unlimited':credit.get('unlimited') is True,'unit':None}
        groups.append({"id":str(key),"name":str(name).replace('\n',' ')[:70],"windows":windows,'balance':balance,
            "reached":item.get("rateLimitReachedType"),"ordinary_allowed":limits.get("ordinaryUsageAllowed")})
    credits=None;summary=limits.get("rateLimitResetCredits")
    if isinstance(summary,dict):
        count=summary.get("availableCount");count=count if isinstance(count,int) and not isinstance(count,bool) and count>=0 else None
        details=summary.get("credits");rows=None
        if isinstance(details,list):
            rows=[]
            for row in details[:100]:
                if not isinstance(row,dict):continue
                expiry=timestamp(row.get("expiresAt"));status=row.get("status")
                labels={"available":"可用","redeeming":"使用中","redeemed":"已使用","unknown":"状态待确认"}
                local_expired=expiry is not None and now>=expiry and status=="available"
                label="已到期 · 待确认" if local_expired else labels.get(status,"状态待确认")
                if status=="available" and expiry and 0<expiry-now<=86400:label="即将到期"
                rows.append({"status":status,"label":label,"expiry":expiry,"no_expiry":"expiresAt" in row and row["expiresAt"] is None,
                    "title":str(row.get("title") or "额度重置卡").replace('\n',' ')[:60],"granted_at":timestamp(row.get("grantedAt"))})
        credits={"count":count,"rows":rows}
    restricted=limits.get('ordinaryUsageAllowed') is False
    return {"status":"ready","message":"常规用量受限 · 请查看官方账户提示" if restricted else "已同步账户额度","account_key":account_key,"plan":str(result.get("plan") or "未知计划"),
        "source":result.get("source","本机 Codex CLI"),"identity_confirmed":True,"observed_at":now,"groups":groups,"credits":credits}


def selected_group(state,config):
    groups=state.get("groups") or []
    return next((g for g in groups if g["id"]==config.get("group")),groups[0] if groups else None)


def selected_window(state,config):
    group=selected_group(state,config)
    windows=group["windows"] if group else []
    return next((w for w in windows if w["role"]==config.get("window","primary")),None)


def recent_for_selection(state,config,role=None):
    target={**config,'window':role} if role else config
    window=selected_window(state,target)
    if not window:return None
    recent=(state.get('recent_by_window') or {}).get(window['key']) or state.get('recent') or {}
    expected={'account':state.get('account_key'),'window':window['key'],'basis':window['basis'],'hours':config.get('hours',1)}
    return recent if recent.get('scope')==expected else None


def reset_parts(window,now):
    if not window:return []
    due=window.get('resets_at')
    if due is None:return [('—','value')]
    seconds=max(0,int(due-now))
    if seconds==0:return [('待确认','label')]
    minutes=seconds//60;days,minutes=divmod(minutes,1440);hours,minutes=divmod(minutes,60)
    if days:return [(str(days),'value'),('d','label')]+([(str(hours),'value'),('h','label')] if hours else [])
    if hours:return [(str(hours),'value'),('h','label')]+([(str(minutes),'value'),('m','label')] if minutes else [])
    return [(str(minutes),'value'),('m','label')] if minutes else [('<1','value'),('m','label')]

def strip_values(state,config,now):
    window=selected_window(state,config)
    if state.get("status") not in ('ready','stale') or not state.get('account_key'):window=None
    credits=state.get("credits") or {};recent=recent_for_selection(state,config) or {};identity=state.get('status') in ('ready','stale') and bool(state.get('account_key'))
    prefix=(f"{window['minutes']/60:g}h" if window and window.get("minutes") and window['minutes']<1440 else
            f"{window['minutes']/1440:g}d" if window and window.get("minutes") else "额度")
    due=bool(window and window.get("resets_at") and now>=window['resets_at'])
    fresh=state.get('status')=='ready' and now-state.get('observed_at',0)<=120
    parts={
      'reset':reset_parts(window,now),
      'recent':[(quota_percent(recent['spent'],False),'value'),('%','label')] if window and recent.get('spent') is not None else [],
      'quota':[(quota_percent(window['remaining'],False),'value'),('%','label')] if window else [],
      'credits':[(str(credits['count']),'value'),('张','label')] if identity and credits.get('count') is not None else []}
    return {"quota":quota_percent(window['remaining']) if window else "—",
        "reset":"".join(text for text,role in reset_parts(window,now)) if window else "—",
        "recent":quota_percent(recent['spent']) if window and recent.get('spent') is not None else "—",
        "credits":str(credits['count']) if identity and credits.get('count') is not None else "—",
        "capsule":"账户余 "+quota_percent(window['remaining']) if window and not due else "重置待确认" if due else None,
        "pending":due,'parts':parts}
