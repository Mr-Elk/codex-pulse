"""Portable local stdio bridge for a future macOS shell. No listening port."""
import argparse
import copy
import json
from pathlib import Path
import sys
import threading
import time

from quota_model import strip_values,recent_for_selection
from quota_service import QuotaService
from quota_config import clean_config,load_config
from quota_source import CodexQuotaSource
from settings_store import read_document,write_document


def settings_path():
    if sys.platform=='darwin':return Path.home()/'Library/Application Support/CodexPulse/settings.json'
    from overlay_settings import default_path
    return default_path()


def persist_config(path,config):
    value,_=read_document(path)
    value['quota']=clean_config(config)
    write_document(path,value)


class Bridge:
    def __init__(self,path,emit,source=None):
        self.path=path;self.emit=emit;self.config=load_config(path)
        self.lock=threading.Lock();self.state={'status':'loading','groups':[]}
        self.service=QuotaService(path.with_name('quota-history.sqlite3'),self.config,self.update,source)

    def update(self,state):
        with self.lock:self.state=copy.deepcopy(state)
        self.emit({'event':'quota','state':self.snapshot()})

    def snapshot(self):
        with self.lock:
            state=copy.deepcopy(self.state);config=copy.deepcopy(self.config)
        if recent_for_selection(state,config) is None:state.pop('recent',None)
        return {**state,'config':config,'strip':strip_values(state,config,time.time())}

    def request(self,message):
        if not isinstance(message,dict):raise ValueError('消息格式不可用')
        method=message.get('method')
        if method=='state':return self.snapshot()
        if method=='refresh':self.service.refresh();return {'accepted':True}
        if method=='configure':
            config=clean_config(message.get('config'))
            persist_config(self.path,config)
            with self.lock:self.config=config
            self.service.configure(config)
            return {'config':config}
        if method=='history/clear' and message.get('confirmed') is True:
            self.service.clear_history();return {'accepted':True}
        raise ValueError('不支持此操作，或尚未确认清除本机历史')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--settings-file',type=Path,default=settings_path())
    parser.add_argument('--codex-cli',type=Path)
    parser.add_argument('--once',action='store_true',help='Read once, print sanitized normalized state, then close')
    args=parser.parse_args();write_lock=threading.Lock()
    def emit(value):
        with write_lock:print(json.dumps(value,ensure_ascii=False),flush=True)
    bridge=Bridge(args.settings_file,emit,CodexQuotaSource(args.codex_cli))
    try:
        if args.once:bridge.service.read_once();return
        bridge.service.start()
        while True:
            line=sys.stdin.readline(1_000_001)
            if not line:break
            identity=None
            try:
                if len(line)>1_000_000:raise ValueError('消息过长')
                request=json.loads(line);identity=request.get('id') if isinstance(request,dict) else None
                emit({'id':identity,'result':bridge.request(request)})
            except (ValueError,OSError):emit({'id':identity,'error':'本机设置或操作暂不可用；原设置已保留'})
    finally:bridge.service.close()


if __name__=='__main__':main()
