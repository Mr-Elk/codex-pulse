# Codex Pulse v0.7.0-beta.10 · Windows 公开测试版

Windows 设置与统计条按 v19 整理，修复设置打开时的悬浮详情、显示方式切换后的层级、Esc 取消误退出、拖动排序及实时宽度带来的跳动。支持 Windows 11 x64，需要已有 Python 3.10+（含 Tkinter）与 Windows PowerShell；无需 API Key 或第三方 Python 包。

## 下载与安装

- 下载 `codex-pulse-0.7.0-beta.10-windows.zip`，完整解压后双击“安装内测版.cmd”。请勿只取内部 payload ZIP。
- 升级和回退保留设置；随包固定提供已校验的 beta.6 恢复基线。保留旧版本和备份，遇到校验冲突时安装器保护已有文件。
- 账户额度按来源提供的真实窗口显示；单个窗口铺满整行。额度和余额展示整数，来源未给出货币单位时明确说明。最近用量为本机快照估算，缺失不补算，账户数据与本机记录状态分开显示。
- Logo 控制展开、收起；数据悬浮查看详情。面板跟随统计条。设置打开、关闭、重开和显示方式往返切换已实际核对。

## 已验证与仍待验证

328 项回归通过，无失败、错误或跳过。实际完成公开旧版升级、含中文及空格路径新装、beta.10 → beta.6 → beta.10，保留设置。最终运行载荷完成同一进程 30 分钟双模式采样：881 次，0 异常；桌面 11.2 分钟，输入框上方 18.7 分钟。49 次桌面宽度变化未记录到左侧锚点异常。

本版为公开测试版。另一台物理 Windows 电脑、真实生成中断、睡眠唤醒及多屏混合 DPI 仍待实测，不声明为稳定版。验收模式下设置窗口在焦点变化后保持打开，不能据该长测声明普通启动的失焦关闭行为已通过。30 分钟资源采样也不等于逐帧证明全程没有闪烁。

## Mac 状态

Mac 原生窗口和 Apple Silicon 安装包尚未完成。当前只有共享额度后端、stdio 接口和独立实现方案；没有 Mac 原生构建、签名、公证或真机验收。Windows 包不能在 Mac 上使用。具体方案见仓库 MACOS.md。

## 校验与恢复

运行载荷 SHA256：`d69719bf8c89e85ce66b8374d6e69c6ed708ebf35df780ced19fa762d4a8d7de`。公开封装仅更新发布说明和外层文档，运行载荷、安装器及管理工具保持已验证内容。哈希用于一致性校验，不是代码签名。公开演示截图为合成数据，不包含真实账户或会话。

卸载或问题排查前保留独立 data 目录。公开旧版及本版发行资产均保留；需要恢复时使用随包 beta.6 回退入口，不覆盖现有设置。

This is a Windows prerelease, not a stable or macOS release. Python 3.10+ with Tkinter and Windows PowerShell are required. The frozen runtime passed 328 checks and a 30-minute dual-mode native sample; other-machine, real interruption, sleep/wake and mixed-DPI acceptance remain open. Mac currently has shared backend code and an implementation plan only. Use the Windows ZIP, extract it fully, and run 安装内测版.cmd. Preserve the separate data directory during upgrade and recovery.
