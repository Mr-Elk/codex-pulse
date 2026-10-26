"""Official local app-server client. Never opens auth files or starts model turns."""
import json
import os
from pathlib import Path
import queue
import shutil
import subprocess
import threading
import hashlib


class QuotaSourceError(Exception):
    def __init__(self,message,account_key=None):
        super().__init__(message);self.account_key=account_key


class CodexQuotaSource:
    ALLOWED = {"initialize", "account/read", "account/rateLimits/read"}

    def __init__(self, executable=None, timeout=15):
        self.executable = executable
        self.timeout = timeout
        self.process = None
        self.messages = queue.Queue()
        self.lock = threading.Lock()
        self.serial = 0

    def _reader(self, process, messages):
        try:
            for line in process.stdout:
                if len(line) > 2_000_000:
                    continue
                try:value = json.loads(line)
                except ValueError:continue
                if isinstance(value, dict) and "id" in value:messages.put(value)
        except (OSError, ValueError):pass
        finally:messages.put(None)

    def _request(self, method, params=None):
        if method not in self.ALLOWED:
            raise QuotaSourceError("Unsupported account operation")
        process=self.process
        if process is None:raise QuotaSourceError("账户连接已关闭")
        self.serial += 1
        identity = self.serial
        process.stdin.write(json.dumps({"id":identity,"method":method,"params":params or {}})+"\n")
        process.stdin.flush()
        while True:
            try:response=self.messages.get(timeout=self.timeout)
            except queue.Empty:raise QuotaSourceError("读取额度超时，请稍后刷新") from None
            if response is None:raise QuotaSourceError("本机账户连接已断开")
            if response.get("id") != identity:continue
            if "error" in response:
                # Do not surface raw server errors, paths, auth data or stderr.
                raise QuotaSourceError("当前登录或服务暂未提供额度数据")
            result=response.get("result")
            if not isinstance(result,dict):raise QuotaSourceError("额度响应格式不可用")
            return result

    def _start(self):
        if self.process is not None and self.process.poll() is None:return
        executable=self.executable or os.environ.get("CODEX_CLI_PATH") or shutil.which("codex.exe") or shutil.which("codex")
        if not executable:raise QuotaSourceError("未找到本机 Codex CLI，请先安装并登录官方客户端")
        self.messages=queue.Queue()
        self.process=subprocess.Popen([str(executable),"app-server","--stdio"],stdin=subprocess.PIPE,stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,text=True,encoding="utf-8",bufsize=1,
            creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
        threading.Thread(target=self._reader,args=(self.process,self.messages),daemon=True).start()
        self._request("initialize",{"clientInfo":{"name":"codex_pulse","title":"Codex Pulse","version":"0.7.0-beta.10"},
                                    "capabilities":{"experimentalApi":True}})
        self.process.stdin.write('{"method":"initialized","params":{}}\n');self.process.stdin.flush()

    def read(self):
        with self.lock:
            before=None
            try:
                self._start()
                before=self._request("account/read",{"refreshToken":False})
                account=before.get("account") or {}
                if account.get("type")!="chatgpt":raise QuotaSourceError("此登录方式不提供 ChatGPT 账户额度")
                limits=self._request("account/rateLimits/read")
                after=self._request("account/read",{"refreshToken":False})
                def route(v):
                    a=v.get("account") or {};r=v.get("workspaceRouting") or {}
                    return a.get("type"),a.get("email"),a.get("planType"),r.get("chatgptAccountId")
                if route(before)!=route(after):raise QuotaSourceError("账户正在切换，请重新刷新")
                routing=(after.get("workspaceRouting") or {}).get("chatgptAccountId")
                account_id=limits.get("accountId") or routing
                if routing and limits.get("accountId") and routing!=limits["accountId"]:
                    raise QuotaSourceError("额度账户与当前账户不一致，请重新刷新")
                return {"account_id":account_id,"plan":account.get("planType"),"limits":limits,"source":"本机 Codex CLI"}
            except (OSError,ValueError,QuotaSourceError) as error:
                confirmed=None
                # A failed quota request may retain a snapshot only after a
                # second identity read confirms the very same workspace.
                try:
                    if isinstance(before,dict) and not ('不一致' in str(error) or '切换' in str(error)):
                        after=self._request('account/read',{'refreshToken':False})
                        def identity(v):
                            a=v.get('account') or {};r=v.get('workspaceRouting') or {}
                            return a.get('type'),a.get('email'),a.get('planType'),r.get('chatgptAccountId')
                        route=identity(before)
                        if route==identity(after) and route[0]=='chatgpt' and route[3]:confirmed=hashlib.sha256(str(route[3]).encode()).hexdigest()
                except (OSError,ValueError,QuotaSourceError):pass
                self.close()
                if isinstance(error,QuotaSourceError):
                    # Explicit account mismatch must never reuse the prior one.
                    if '不一致' in str(error) or '切换' in str(error):confirmed=None
                    raise QuotaSourceError(str(error),confirmed) from None
                raise QuotaSourceError("无法连接本机额度服务，请确认官方 CLI 可用",confirmed) from None

    def close(self):
        process,self.process=self.process,None
        if process is None:return
        try:
            if process.stdin:process.stdin.close()
            process.wait(timeout=.5)
        except (OSError,ValueError,subprocess.TimeoutExpired):
            if process.poll() is None:
                process.terminate()
                try:process.wait(timeout=2)
                except subprocess.TimeoutExpired:pass
        finally:
            if process.stdout:process.stdout.close()
