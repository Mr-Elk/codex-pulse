# 开发与测试

需要 Windows、Python 3.10+（含 Tkinter）和 PowerShell。核心代码仅用标准库与 Windows API；背景模糊的 C++ 构建工具是可选开发依赖。

开发与重构遵循 [ENGINEERING.md](ENGINEERING.md)。本文件统一维护检查命令；从项目源码根目录执行。

## 按影响选择检查

| 修改范围 | 适用检查 |
| --- | --- |
| 仅文档、注释或格式，行为未改变 | 内容、引用、命令入口与差异检查；涉及可执行格式变化时补充语法检查 |
| 配置、历史恢复或额度规则 | 快速额度回归，并补充受影响模块已有测试 |
| 设置、菜单、弹窗、悬停提示或统计条 | 界面回归及 AGENTS.md 要求的实机操作和截图检查 |
| 跨模块依赖、后台交互或配置兼容 | 完整回归；界面有变化时同时完成人工检查 |

完整回归已包含的分组无需重复执行。测试数量以本轮实际输出为准；自动化通过不能替代真实界面、长期运行或异机验收。

## 快速额度回归

```powershell
python -X utf8 -B -m unittest test_quota_config test_history_recovery test_quota -q
```

## 界面回归

```powershell
python -X utf8 -B -m unittest test_usage_records test_ui_layout_rules test_product_ui test_quota test_quota_regressions test_v19_fidelity -q
```

这组保留项目要求的界面相关检查。界面修改同时保留已确认的 SVG/Logo 几何、主题同步、字体角色、固定统计身份和个人设置兼容性。

## 完整回归

```powershell
python -X utf8 -B -m unittest discover -q
```

## 环境与失败判断

测试会创建受控 Tk 窗口、临时目录和测试子进程。桌面回归前确认 Tk、项目字体、PowerShell 及可写临时目录可用；仅为测试进程设置 TEMP/TMP，不改系统级环境。

操作被拒绝、缺少桌面或字体加载失败时，先保留失败输出，用最小复现或已有基线判断原因。环境阻断与业务回归分别报告，完成不受影响的检查，再在具备授权与依赖的环境复核；不能仅凭经验把失败归因于环境，也不能通过放宽业务断言消除失败。

## 已有场景入口

以下为按问题查找测试的示例，不代表完整覆盖或最新通过结果：

| 场景 | 测试入口 |
| --- | --- |
| 本地历史库占用后的刷新恢复、清空历史与错误撤销 | test_history_recovery.py |
| 旧配置加载及配置模块的依赖边界 | test_quota_config.py |
| 带空格路径下的 PowerShell 判定函数调用 | test_composer_wrapper.py |
| 账户隔离、缺失数据、用量累计和提醒规则 | test_quota.py、test_quota_regressions.py |

## 分发与资料

发布文件使用 release_tools.py 生成并核对 SHA256，包含 LICENSE。DLL、PNG 导出、安装包、截图、缓存与本机数据不提交源码；预编译 DLL 和界面示例作为 Release 附件提供。

请勿在 Issue、提交或附件中包含个人设置、会话数据、原始日志、私有安装指针或凭据。使用示例数据复现问题。
