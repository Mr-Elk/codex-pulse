# Codex Pulse 内测使用说明

版本：0.6.18-beta.5。Beta 预发布，供内测与反馈。

## 环境

- 本轮支持范围为 Windows 11 x64、本机 Codex 工作会话。
- 已安装 Python 3.10+，包含 Tkinter，并能在终端运行 python.exe。
- Windows PowerShell。无需 API Key、第三方 Python 包或 C++ 编译器。
- 安装器不下载软件、不添加开机启动、不改变系统策略、不修改 Codex 安装目录。

## 安装和启动

1. 将整个内测 ZIP 解压到一个普通文件夹，保留 payload ZIP 与 tools 文件夹。
2. 双击“安装内测版.cmd”。默认安装到当前用户 LOCALAPPDATA/CodexPulseBeta。
3. 安装完成后，在安装目录双击“启动统计条.cmd”。
4. 左侧手柄单击切换胶囊，再单击返回；拖动手柄移动；右侧省略号打开设置。

高级用法：`powershell -NoProfile -File install.ps1 -InstallRoot "D:/Apps/CodexPulseBeta"`。
若 Python 未安装，先自行安装带 Tk 的 Python；本包不会代为安装。
内测安装使用独立的 data/settings.json，不覆盖原有正式/开发版设置。关闭原统计条后再启动内测版，单实例保护会阻止重叠运行。

## 升级、回退和关闭

下一个内测包解压后，再运行安装脚本并选择同一安装目录。安装器先核对旧文件，再正常关闭属于该安装目录的窗口；保留 data 内的主题、字号和位置。
双击安装目录“回退上一版.cmd”切回上一个保留版本；个人设置继续保留。首次安装没有上一版，会明确提示并保持现状。
若用户修改了版本文件，校验失败会停止升级/回退，保留改动和备份。不会强行覆盖或清理旧版本。
设置底部“关闭统计条”退出；启动后不会自动重启。

## 检查状态和反馈

“检查运行状态.cmd”会核对进程创建时间及心跳。running=true 只在进程身份与新鲜心跳同时成立时有效；unknown/unresponsive 不能算已启动。
状态位于安装目录 data/runtime.json；退出记录位于 data/logs/lifecycle.jsonl，错误输出位于 data/logs/last-stderr.log。记录只保存在本机，不自动上传。
反馈请提供版本、显示模式、Windows 缩放、复现步骤。原始状态和日志可能包含本机路径或会话标题，分享前请检查并删去私人信息。

## 仍需内测的范围

真实 Codex 生成中追加消息与中断提示、长时间开关设置、多显示器和混合 DPI、其他电脑的环境兼容性。
自动化受控中断场景不等于真实 Codex 中断提示的现场验收。TPS 是请求平均估算；云端或缺少本地用量的历史会话不支持。语言切换尚未提供。
