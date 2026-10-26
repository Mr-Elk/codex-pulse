# macOS / Apple Silicon 进度

2026-10-23：以下是 v19 的独立实现方案。本轮未编写 Mac 原生界面、未构建 Mac 包、未申请权限、未签名或发布。共享数据后端已有代码和 Windows 受控测试；Mac 实读、权限及视觉表现需要 Mac mini 验证。

## v19 实施顺序

1. **数据适配与启动生命周期**：沿用 quota_source / model / history / service 的账户身份、余额单位、窗口时长与重置卡规则。通过本地 stdio 传递规范化快照，限制请求白名单。补充临时详情范围查询，不能借持久 configure 改写统计条范围。独立测试服务退出、超时与重启。
2. **先完成桌面悬浮**：建议 AppKit NSPanel 承载，原生材质与菜单栏恢复入口。先完成账户页、独立余额/重置卡、来源说明、统一下拉和详情返回，再接统计条与胶囊。Logo 仅展开/收起及拖动；数据只读悬浮；36/40/44pt 对应 13/15/17pt 与 16/18/20pt 图标，Retina 按 backing scale 渲染。此阶段按设计不需要读取其他应用 UI。
3. **实现会话来源与跟随**：读取本机未归档会话目录；候选确认后才绑定。桌面方式可单独使用。输入框跟随使用辅助功能探测，仅在用户选择该方式时引导授权；没有权限或找不到可靠输入框时明确说明并允许继续桌面方式。不能猜测同名会话或沿用旧页面坐标。仅读取必要的导航标题和输入框几何，不读取模型消息正文。
4. **点击穿透与可恢复性**：验证原生窗口的命中策略。整窗忽略鼠标会影响 Logo 与指标悬浮，不能直接把 Windows 标志位替换为整窗 ignoresMouseEvents。建议区分背景与可交互区域的原生命中层，并用本应用内部跟踪处理悬浮；先做最小原型验证焦点、拖动、多屏和菜单栏恢复，再接完整页。
5. **Mac mini 真机验收**：Apple Silicon 启动、实际 CLI 身份/额度、JSONL 会话数据、睡眠唤醒缺口、过期加记录不全、Space/全屏、多屏与 Retina、跟随/固定确认取消、托盘恢复、退出子进程。若要支持 Intel，单独决定构建范围，不默认承诺。

以上原生容器和命中层属于实施建议，尚未经 Mac 验证。可访问性信任状态依据 [AXIsProcessTrusted](https://developer.apple.com/documentation/applicationservices/1460720-axisprocesstrusted) 检查；窗口鼠标处理参考 [ignoresMouseEvents](https://developer.apple.com/documentation/appkit/nswindow/ignoresmouseevents)。默认不申请录屏或完全磁盘访问；遇到具体文件访问限制时再定位最小需要的访问。

发布前另行准备可回退的 .app/安装包、版本与升级迁移、签名以及公证。公开直接分发按照 Apple 的 [签名流程](https://developer.apple.com/documentation/xcode/creating-distribution-signed-code-for-the-mac/) 和 [公证流程](https://developer.apple.com/documentation/security/notarizing-macos-software-before-distribution) 处理；发布授权与实现授权分开。本轮只交付方案。

这次额度功能采用平台无关的 `quota_source.py`、`quota_model.py`、`quota_history.py`、`quota_service.py`。Windows 界面已经接入同一套实现。Mac 原生窗口仍待实现和 Mac mini 真机验证，当前 Windows 安装包不能作为 Mac 安装包使用。

## 可复用的本机后端

共享核心开发入口已按工程规范整理：quota_config 维护配置规则，session_titles 与 active_chat 负责纯标题/绑定规则，settings_store 统一设置读写，quota_source 管理带截止时间的本机协议和所属子进程。Windows 界面继续复用这些模块，旧配置及既有配置导入入口保留兼容。

在源码根目录先运行 [CONTRIBUTING.md 的共享核心回归](CONTRIBUTING.md#共享核心回归)。该组不需要 Windows、Tk 或原生材质库，使用隔离文件、数据库与子进程；Windows 上通过该组只能说明本地共享逻辑正常，Mac 实际 CLI、信号和退出行为仍须真机复核。

接续开发时先保留下面的 stdio 协议与账户只读白名单，再实现原生容器。退出测试须覆盖 CLI 实际启动方式及其所属子进程；测试中的终止信号故障注入不代表已完成 Mac 进程树验收。

需要 Python 3.10+ 和已登录的官方 Codex CLI。Mac 本地设置与快照位于 `~/Library/Application Support/CodexPulse/`。

```sh
python3 quota_backend.py --codex-cli "$(command -v codex)" --once
python3 quota_backend.py --codex-cli "$(command -v codex)"
```

第二种方式通过标准输入/输出交换 JSON 行，不监听网络端口。`state` 获取快照；`refresh` 请求刷新；`configure` 保存额度设置；`history/clear` 需要 `confirmed: true`。后台发出 `event: quota` 推送。额度、历史算法和提醒去重与 Windows 共用。接口没有消耗重置卡、登录、退出账号或发起模型请求的方法。

```json
{"id":1,"method":"configure","config":{"window":"primary","hours":6,"capsule":"quota","reminder":{"enabled":false,"source":"focus","threshold":20}}}
```

生产界面还需 AppKit NSPanel / NSVisualEffectView 与菜单栏承载此协议，并重用已确认的 SVG、字体与主题。桌面额度模式无需辅助功能权限；输入框跟随模式另行实现 AX 探测与授权说明。不得用不透明的底色模拟原生毛玻璃，不默认申请录屏或完全磁盘权限。

## Mac mini 发布前验收

- arm64 原生构建、签名与公证，安装升级及回退。
- 实际账户读取、窗口名与时区、睡眠唤醒后的覆盖缺口。
- NSPanel 拖拽、胶囊左侧中心展开、多屏与缩放、切页和中断消息显隐。
- 通知授权、重复提醒、退出时关闭本应用创建的 app-server 子进程。

Windows 测试和模拟 `darwin` 的单元测试只能证明共享逻辑，不代表上述 Mac 真机验收通过。
