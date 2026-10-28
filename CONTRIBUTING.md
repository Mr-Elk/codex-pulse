# 开发与测试

需要 Windows、Python 3.10+（含 Tkinter）和 PowerShell。核心代码仅用标准库与 Windows API；背景模糊的 C++ 构建工具是可选开发依赖。

开发与重构遵循 [ENGINEERING.md](ENGINEERING.md)。本文件统一维护检查命令；从项目源码根目录执行。

每次提交的文档同步、版本与环境更新条件、候选打包和公开发布顺序见 [WORKFLOW.md](WORKFLOW.md)。普通提交不要求更新所有版本号或重配个人环境。

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


## GitHub Actions

Windows 的 `Tests` 工作流在 PR、main 推送及手动触发时使用 Python 3.10 和 3.12。调用 `ci/run_windows_tests.py` 先检查真实 Tk 窗口、Windows 图形库和 Windows PowerShell，再执行上面的完整回归。环境检查失败时停止，不把后续成功步骤覆盖成通过。

```powershell
python -X utf8 -B ci/run_windows_tests.py --log-dir ci-logs
```

环境和回归分别保留 `preflight.log`、`unittest.log`，成功或失败均上传日志；保留子进程退出码，启动失败和超时明确失败。环境检查上限 45 秒、回归上限 900 秒，整个作业上限 20 分钟。运行器本身的跨平台故障检查：

```sh
python3 -X utf8 -B -m unittest ci.test_ci_runner -v
```

CI 工具和自身测试集中在 `ci/`，由源码仓库的完整回归自动发现。Windows 运行载荷不包含 CI；开发载荷按明确清单保留测试及其依赖，不能靠自动收集根目录文件补依赖。

Actions 固定完整提交 SHA，使用只读权限；外部 PR 仍遵守仓库的运行批准要求。CI 的受控窗口测试不代替真实桌面、目标缩放、截图或异机验收，不触发打包或发布。

## 文档链接检查

需要 Python 3.10+ 和 Git，可在 Windows、macOS 或 Linux 上执行：

```sh
python -X utf8 -B -m unittest ci.test_doc_links -v
python -X utf8 -B ci/check_doc_links.py
```

检查 Git 跟踪的 Markdown 中的本地链接、图片和 Markdown 锚点；新增文件需先暂存。支持常用行内与引用链接、标题、URL 编码及显式 HTML 锚点，忽略围栏代码、行内代码和 HTML 注释。它不检查外网可用性、HTML 文件内部锚点，也不是完整 Markdown 渲染器。失败会显示源文件、行号和目标。

Docs 工作流在所有 PR、main 推送和手动运行时执行以上检查，因此仅删除或重命名目标文件也会触发；本机忽略文件不能让链接误通过。

## 发布一致性检查

当前主分支的门禁覆盖 Windows：`plugin.json` 是产品版本来源，`product_version.py` 读取它，账户连接不再维护另一个版本常量。共享额度客户端允许调用入口显式传入 `client_version`；Mac/CLI 合入时应分别传入自身版本并补齐该模块的分发依赖，不能沿用 Windows 版本或因此发布 CLI。

```sh
python -X utf8 -B -m unittest ci.test_release_consistency test_product_version test_release_tools -v
python -X utf8 -B ci/check_release.py
```

第二条检查当前工作文件，适用于提交前。检查 Windows 安装器的候选/回退版本、明确文件清单、Python 字面量导入依赖、LICENSE、候选指南版本，以及**实际入包文件之间**的文档链接和锚点。两种语言的公开 README 指向公开版本的固定指南，不跟随开发候选。检查失败返回非零状态。

`distribution/windows-package.json` 明确列出 `runtime`、`development` 和可选原生 DLL；没有通配符，新增文件不会自动入包。新增本地依赖要随调用方加入清单。包内 README 从 `.md.in` 模板生成，版本取自 `plugin.json`；BETA_GUIDE 和 RELEASE_NOTES 的内容及版本仍需在候选变化时审阅。历史验证材料仅留在开发资料中，不能作为当前运行载荷的验收证据。

提交后或发布准备时，从干净的 Git 检出检查来源；新 `Release consistency` 工作流在所有 PR、main 推送和手动运行时自动执行：

```sh
python -X utf8 -B ci/check_release.py --require-clean
```

在已获打包授权并生成实际 Windows 载荷后，从**构建所用的同一源码提交**核对归档：

```sh
python -X utf8 -B ci/check_release.py --require-clean --archive /path/to/windows-payload.zip --profile runtime
```

开发载荷使用 `--profile development`。该命令复用 `release_tools.verify_archive` 校验，再对照源码清单核对每个文件、摘要、平台、版本和源码提交；即使有人重算了包内校验值，漏文件、混入其他平台或旧源码归档仍失败。它不会构建、安装或发布。

`release_tools.build_archive` 保留原有 `include_tests` 接口，分别选择开发或运行清单；新归档格式记录 `platform`、`profile`、`source_revision`，并拒绝覆盖已有输出。非 Git 或有未提交内容的实验/测试载荷会记录空的来源，不能通过发布归档来源核验。已有旧格式回退包继续使用原校验流程，不要求重写旧资产。测试只在临时目录构造小型夹具包。

该检查不等于完整安装外壳、原生 DLL 构建来源、签名、长期运行或实机界面验收；这些仍须针对实际候选另行验证。Mac/CLI 尚未合入本分支的打包器不由 Windows 门禁代验，已有本地包也不因本次合并而获准发布。
