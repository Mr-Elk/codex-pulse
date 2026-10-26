# Codex Pulse

简体中文 | [English](README.en.md)

Windows 上的本地 Codex 会话统计条。查看 Token 用量、平均 TPS 估算、缓存命中率、上下文占用及轮次/请求数。

**Windows 公开测试版：0.7.0-beta.10**。主要支持 Windows 11 x64；需要 Python 3.10+（包含 Tkinter）和 Windows PowerShell。运行时无需 API Key 或第三方 Python 包。

![统计条示例](https://github.com/Mr-Elk/codex-pulse/releases/download/v0.7.0-beta.10/toolbar.png)

## 下载与启动

1. 从[发行页](https://github.com/Mr-Elk/codex-pulse/releases/tag/v0.7.0-beta.10)下载 `codex-pulse-0.7.0-beta.10-windows.zip`。截图使用当前界面与演示数据，不包含真实账户或会话。
2. 将整个 ZIP 解压到普通文件夹，双击 **安装内测版.cmd**。
3. 安装后在 `%LOCALAPPDATA%/CodexPulseBeta` 双击 **启动统计条.cmd**。
4. 打开本机 Codex 工作会话。识别不到时，从省略号设置的“统计条 → 统计对象与范围”选择并确认固定。

请下载 Windows 安装包；GitHub 自动生成的 Source code ZIP 用于开发，不包含预编译背景模糊 DLL。若缺少 Python，安装器会提示并停止，不会自动安装环境。

本包附带beta.6作为回退基线，不再默认回到有Esc缺陷的beta.5。另一台电脑验收见随包acceptance目录。

完整操作、环境与回退见 [内测指南](BETA_GUIDE.md)。升级时继续选择原安装目录，个人设置位于独立 data 目录；可通过“回退上一版.cmd”切回保留版本。

## 能做什么

- **两种显示方式**：输入框上方跟随，或跨应用保留的桌面统计条。显示方式在设置中选择。单击左侧 Logo 展开/收起，拖动 Logo 移动。
- **自动跟随与固定会话**：只把未归档的本地工作会话放入选择列表，支持搜索；归档后移除，解除归档后恢复。
- **主题与字号**：十二组预设及自定义 HEX/HSV 取色；统计条、设置面板和滑块同步变色。
- **SVG 与玻璃质感**：统一图标、圆角、白色内沿及抗锯齿；不支持实时模糊时回落到半透明底。
- **简洁滚动**：滑块位于内容外侧，静止隐藏，滚动时浮现，悬停/拖拽加粗；显隐不挤压文字。
- **本地运行**：只读本机记录，不调用模型、不上传会话、不修改 Codex 安装文件，也不增加开机自启。

![显示设置示例](https://github.com/Mr-Elk/codex-pulse/releases/download/v0.7.0-beta.10/settings-display.png)

## 指标与支持范围

| 指标 | 含义 |
|---|---|
| TPS | 最近完成请求的输出 Token ÷ 请求耗时估算，包含网络和首 Token 等待；生成中不复用旧速度 |
| Token | 会话累计输入与输出；输入含重复发送的上下文，推理 Token 已包含在输出中 |
| 缓存 | 最近请求的已缓存输入占比 |
| 上下文 | 最近请求的输入加输出占记录窗口的比例，属于估算 |
| 轮次 / 请求 | 累计后台任务轮次 / 模型请求数，轮次不等于用户消息对数 |

自动跟随通过可访问性导航标题匹配本地显示名，只接受唯一匹配；同名或不可识别时清空旧数字，可手动固定。仅支持本机仍保留 JSONL 用量记录的会话，不支持从云端或其他电脑恢复统计。缺少记录表示不可用，不表示零。

这是独立 Windows 辅助窗口，不是 Codex 原生输入框扩展，也不是 OpenAI 官方产品。Codex 更新可能改变本地记录或可访问性结构。

## 验证与已知待办

验证范围见 [VALIDATION.md](VALIDATION.md)。受控回归与真实现场验收分开记录；真实生成中追加消息/中断提示、长期连续运行、其他电脑、多显示器和混合 DPI 继续内测。因此本次按预发布版提供。

语言切换、不可用原因诊断及大量会话的性能测量留在 [TODO.md](TODO.md)，额度新功能见下文，本版为公开测试版。

## 从源码运行

在 Windows 上克隆仓库、进入目录，然后运行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\launch.ps1
```

该参数只用于本次脚本进程，不修改系统执行策略。若组织策略禁止执行，请按组织要求运行。

源码不提交编译产物。要重建可选的实时背景模糊 DLL，需要已安装 Visual Studio C++ x64 Build Tools 和 Windows SDK：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\build_native.ps1
```

未构建 DLL 仍可使用半透明底。正常使用建议下载 Releases 中已含 x64 DLL 的 Windows 安装包。

开发与测试见 [CONTRIBUTING.md](CONTRIBUTING.md)，设计约定见 [DESIGN.md](DESIGN.md)。

## 相关项目

- [codex-statusbar](https://github.com/dongyue-19/codex-statusbar)：Windows Codex 工具栏 TPS、Token 与缓存统计。
- [codex-monitor-hud](https://github.com/LH-03/codex-monitor-hud)：Windows 上的 Codex Desktop / CLI 多任务 HUD。
- [CodexBar](https://github.com/steipete/CodexBar)：提供商额度、重置时间等监控，包含 macOS 与 Linux 桌面界面。
- [ccusage](https://github.com/ccusage/ccusage)：本地编码代理用量与估算成本的命令行分析。

这些是独立项目，统计口径与集成方式可能不同，列出不表示兼容或集成。

## 反馈

请在 [Issues](https://github.com/Mr-Elk/codex-pulse/issues) 提供版本、Windows 缩放、显示方式和复现步骤。日志只保存在本机；分享前去掉个人路径、会话标题、UUID 和消息内容。

## 许可证

采用 [MIT](LICENSE)。

## 0.7.0 本机额度预览

省略号 → **账户**：查看账户额度组、主次窗口剩余比例、自然重置时刻和倒计时、重置卡状态及期限。需要已登录的官方 Codex CLI，并支持 `account/rateLimits/read`；接口不可用时显示原因，不猜测数据。使用官方账户连接，不要求额外 API Key；Pulse 不读取认证文件或发起模型请求。账户接口会连接官方服务，因此此功能不是完全离线统计。

**最近用量**提供 1/3/6/24 及自定义 1–168 小时。启用后开始积累，只估算所选窗口的额度百分点，分别显示本机记录完整性、最后记录时刻与账户额度过期状态；区间记录点击后展开。不能用它还原启用前的历史，也不能与会话 Token 等同。历史库在个人设置同目录，保留 14 天。

**统计条**可选择新增的最近用量、剩余额度、自然重置和重置卡，设置关注窗口、时间范围与收起状态的显示内容；空间不足会折叠完整字段。**账户 → 设置提醒**可选窗口与 0–100% 阈值，默认关闭；首次建立基线，穿越阈值后显示本机浮窗。同一周期与阈值去重。重置卡首版只查看数量、状态与到期时间，实际使用请在官方客户端确认。

Mac 复用额度后端，原生窗口与 Apple Silicon 安装包尚未交付；详情与可运行后端命令见 [MACOS.md](MACOS.md)。本版只发布Windows测试包。

## v19 Windows 本地验收

三页结构、独立的收起状态设置、统一下拉、会话确认取消、字号/图标/高度联动及数据来源说明，见 [本轮实现与验证](V19_IMPLEMENTATION.md)。Mac 原生实现单独按 [实施方案](MACOS.md) 推进。
