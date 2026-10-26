"""Read-only, allowlisted evidence for another Windows machine's acceptance."""
import argparse,ctypes,datetime,hashlib,json,os,platform,re,sys
from pathlib import Path
from runtime_state import health,read_json
import manage


def environment():
    value={'os':platform.system(),'python':platform.python_version(),'python_bits':64 if sys.maxsize>2**32 else 32}
    try:
        import tkinter
        value['tkinter']=str(tkinter.TkVersion)
    except ImportError:value['tkinter']=None
    if sys.platform=='win32':
        v=sys.getwindowsversion();value['windows_version']=[v.major,v.minor,v.build]
        user=ctypes.WinDLL('user32');value['monitors']=int(user.GetSystemMetrics(80))
        try:value['system_dpi']=int(user.GetDpiForSystem())
        except AttributeError:value['system_dpi']=None
    return value


def collect(target,baseline=None,probe=health,env=None):
    target=Path(target);marker=read_json(target/'installation.json')
    result={'schema':1,'at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'environment':environment() if env is None else env,'installation':{'managed':marker.get('name')=='codex-pulse-beta'},'manual_results':'Fill the supplied checklist; this collector does not claim visual or gesture acceptance.'}
    if not result['installation']['managed']:return result
    for key in ('current','previous','recovery_baseline'):
        v=marker.get(key);result['installation'][key]=v if isinstance(v,str) and re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+(?:-[A-Za-z0-9.-]+)?',v) else None
    try:manage.verify_version(target,marker['current']);result['file_integrity']=True
    except (OSError,ValueError,KeyError):result['file_integrity']=False
    state=probe(target/'data/runtime.json')
    result['runtime']={key:state.get(key) if state.get(key) in (True,False,None) else None for key in ('running','native_visible','visible','settings_open','compact','context_valid')}
    result['runtime']['display_mode']=state.get('display_mode') if state.get('display_mode') in ('composer','desktop') else 'unknown'
    result['runtime']['render_error']=bool(state.get('render_error'));result['runtime']['presentation_error']=bool(state.get('presentation_error'))
    try:raw=(target/'data/settings.json').read_bytes();digest=hashlib.sha256(raw).hexdigest()
    except OSError:digest=None
    result['settings_sha256']=digest
    if baseline is not None:result['settings_same_as_baseline']=digest is not None and digest==baseline.get('settings_sha256')
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target',type=Path,default=Path(os.environ.get('LOCALAPPDATA',Path.home()/'AppData/Local'))/'CodexPulseBeta')
    parser.add_argument('--output',type=Path)
    parser.add_argument('--compare',type=Path)
    args=parser.parse_args();baseline=read_json(args.compare) if args.compare else None
    result=collect(args.target,baseline)
    output=args.output or Path.cwd()/('pulse-acceptance-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S')+'.json')
    if output.exists():raise ValueError('Result already exists; choose another output filename')
    output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Saved '+output.name+'. No raw settings, paths, chat titles, account IDs or logs were exported.')


if __name__=='__main__':main()
