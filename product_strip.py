"""v19 strip rendering using the approved assets and live account/session values."""
from types import SimpleNamespace
import ctypes as C
from overlay_style import Run, metrics, INSET
from dataclasses import replace
from quota_model import selected_window
from quota_config import clean_config
from product_data import PRESETS
from functools import lru_cache
import theme

def selected_capsule(config):
    c=clean_config(config);return tuple(k for k in (c['capsule_primary'],c['capsule_secondary']) if k)

def scope_label(snapshot,key):
    c=clean_config((snapshot or {}).get('quota_config'));w=selected_window((snapshot or {}).get('quota_state') or {},c)
    if key=='recent':return str(c['hours'])+'h'
    minutes=(w or {}).get('minutes')
    if not minutes:return '—'
    return f'{minutes/1440:g}d' if minutes%1440==0 else f'{minutes/60:g}h' if minutes%60==0 else f'{minutes:g}m'

def icon_width(key,snapshot):
    return 28 if key=='quota' else 24+max(0,len(scope_label(snapshot,key))-2)*6 if key=='recent' else 18

def glyph(renderer,text,x,y,size,ink):
    from strip_renderer import call,RectF
    font=renderer.new('GdipCreateFont','GdipDeleteFont',renderer.family,size,1,2)
    bounds=RectF();call('GdipMeasureString',renderer.g,text,-1,font,C.byref(RectF(0,0,500,100)),renderer.format,C.byref(bounds),None,None)
    call('GdipDrawString',renderer.g,text,-1,font,C.byref(RectF(x-bounds.width/2,y-size*.66,500,100)),renderer.format,renderer.brush(ink))

def draw_icon(renderer,key,x,y,size=18,snapshot=None):
    from svg_art import paint
    width=icon_width(key,snapshot)*size/18
    name='refresh.svg' if key=='transition' else 'metric-'+key+'.svg' if key in ('quota','recent','reset','credits') else key+'.svg'
    ink=theme.statistics_palette()['icon']
    paint(renderer,name,x,y,width,size,{'currentColor':ink,'#72799c':ink,'#8952ee':ink})
    if key in ('quota','recent'):glyph(renderer,scope_label(snapshot,key),x+width*(12.6/28 if key=='quota' else .5),y+size*12/18,8.8*size/18,ink)
    return width

def icon_png(key,owner,dpi=1,size=18):
    from strip_renderer import Renderer
    snapshot={'quota_state':getattr(owner,'quota_snapshot',{}),'quota_config':getattr(owner,'quota_preferences',{})}
    width=icon_width(key,snapshot)*size/18;r=Renderer(round(width*dpi),dpi,height=round(size*dpi))
    try:draw_icon(r,key,0,0,size,snapshot);return r.png()
    finally:r.close()

def displayed_metrics(snapshot):
    s=snapshot or {};capsule=bool(s.get('capsule'))
    if s.get('navigation_pending'):
        from overlay_style import Metric
        keys=selected_capsule(s.get('quota_config')) if capsule else s.get('visible_metrics')
        account={k:v for k,v in metrics({**s,'visible_metrics':keys}).items() if k in ('quota','recent','reset','credits')}
        return {'transition':Metric('transition',(Run('待识别' if snapshot.get('navigation_waiting') else '切换中','label'),)),**account}
    keys=selected_capsule(s.get('quota_config')) if capsule else s.get('visible_metrics')
    data=metrics({**s,'visible_metrics':keys})
    if capsule and len(data)>1:
        secondary=list(data)[1];metric=data[secondary]
        data[secondary]=replace(metric,runs=tuple(Run(r.text,'secondary',r.gap) if r.role in ('value','speed') else r for r in metric.runs))
    return data

@lru_cache(maxsize=96)
def measured_sizes(items,font,recent_label):
    from strip_renderer import Renderer
    renderer=Renderer(1,1,height=40)
    try:
        icon=PRESETS.get(font,PRESETS[15])[1]/(font/15);sizes=[]
        for key,metric in items:
            label_width=28 if key=='quota' else 24+max(0,len(recent_label)-2)*6 if key=='recent' else 18
            reading=sum(renderer.measure(run)+run.gap for run in metric.runs)-(metric.runs[-1].gap if metric.runs else 0)
            sizes.append((key,label_width*icon/18+6+reading+14))
        return tuple(sizes)
    finally:renderer.close()

def layout_width(snapshot):
    s=snapshot or {};data=displayed_metrics(s)
    return sum(value for _,value in measured_sizes(tuple(data.items()),s.get('font_size',15),scope_label(s,'recent')))+(44 if s.get('capsule') else 72) if data else 180

def draw(renderer,snapshot,hovered=False):
    from svg_art import paint
    s=snapshot or {};logical_h=renderer.height/renderer.scale;width=renderer.width/renderer.scale;font=s.get('font_size',15);factor=font/15
    icon=PRESETS.get(font,PRESETS[15])[1]/factor
    renderer.rounded(.5,1.5,width-1,logical_h-2,(logical_h-2)/2,'#187664b4')
    palette=theme.statistics_palette()
    renderer.rounded(1,1,width-2,logical_h-2,(logical_h-2)/2,palette['fill'],palette['border'])
    renderer.rounded(2.5,2.5,width-5,logical_h-5,(logical_h-5)/2,'#00ffffff','#ffffff')
    paint(renderer,'brand.svg',13,(logical_h-icon)/2,icon,icon)
    capsule=bool(s.get('capsule'));data=displayed_metrics(s)
    inset=43;end_pad=1 if capsule else 29;available=width-inset-end_pad
    sizes=dict(measured_sizes(tuple(data.items()),font,scope_label(s,'recent')))
    chosen=list(data)
    # Fold whole metrics when a host is narrow; preserve the user's ordering.
    tolerance=1/renderer.scale
    while len(chosen)>1 and sum(sizes[k] for k in chosen)>available+tolerance:
        victim=next((k for k in ('rounds','context','cache','tokens','speed','credits','reset','quota','recent') if k in chosen),chosen[-1]);chosen.remove(victim)
    if chosen and sum(sizes[k] for k in chosen)>available+tolerance:chosen=[]
    x=inset
    for key in chosen:
        metric=data[key];iw=draw_icon(renderer,key,x,(logical_h-icon)/2,icon,s);text_x=x+iw+6;start=text_x
        for run in metric.runs:
            renderer.text(text_x,run);text_x+=renderer.measure(run)+run.gap
        renderer.diagnostics.append({'key':key,'left':x-4,'right':x+sizes[key]-4,'icon_left':x,'text_left':start,'text_right':text_x-(metric.runs[-1].gap if metric.runs else 0),'baseline':renderer.baseline})
        x+=sizes[key]
    if not data and not capsule:renderer.text(INSET+8,Run('未选择显示指标','label'))
    if not capsule:renderer.svg('ellipsis.svg',width-31,(logical_h-18)/2,18,18)

def install_renderer(cls):cls.draw=draw
