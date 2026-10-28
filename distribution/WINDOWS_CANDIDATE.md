# Windows beta.12 候选构建准备

状态：本分支准备 **0.7.0-beta.12**；尚未执行 Windows 编译、完整安装包生成或实机验收。公开版本仍为 beta.10，CLI 不发布。历史 beta.11 验收仅属于旧包，不复用其摘要或通过数量。

## 固定输入

候选源码需先经过审查、提交并固定到一个干净提交，再在 Windows 建立新的独立检出。不要把有未提交内容的日常目录或已有 DLL 的目录作为输入。版本来源仍为 plugin.json；安装器、BETA_GUIDE、RELEASE_NOTES 已按 beta.12 准备。

`windows-baselines.json` 锁定公开 beta.10 完整安装包、其中升级载荷和 beta.6 恢复载荷。只从[原公开发行资产](https://github.com/Mr-Elk/codex-pulse/releases/download/v0.7.0-beta.10/codex-pulse-0.7.0-beta.10-windows.zip)取输入；命令会检查完整包及内层载荷摘要、版本与控制器恢复常量，不重新生成或覆盖旧包。

```powershell
python -X utf8 -B distribution/windows_candidate.py inputs --baseline D:\PulseInputs\codex-pulse-0.7.0-beta.10-windows.zip
```

检查和构建命令只使用显式输入，不自动下载、安装依赖、连接设备或上传。Windows 构建机需要现有的 Visual Studio C++ x64 Build Tools、Windows SDK、Git、64 位 Python 3.10+（含 Tkinter）和 Windows PowerShell。

## 构建入口

先从已固定提交建立干净检出，再从源码根运行以下命令；替换示例路径，OutputDirectory 必须是源码目录之外的全新目录：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\distribution\build_candidate.ps1 `
  -OutputDirectory 'D:\PulseCandidates\beta12-run-01' `
  -BaselineInstaller 'D:\PulseInputs\codex-pulse-0.7.0-beta.10-windows.zip' `
  -Python 'C:\Python312\python.exe'
```

需要时用 `-VisualStudio` 指定已存在的 Visual Studio 安装路径；脚本不会安装工具链。使用 PowerShell 5.1/Windows PowerShell 执行，Bypass 仅作用于本次进程。组织策略阻止时停止并保留错误，不能修改系统级策略。

入口依次执行干净源码检查、旧包检查、x64 原生编译、完整回归、真实 DLL 加载/创建/尺寸/销毁冒烟检查，再生成完整 ZIP 并回读验证。任何一步失败都停止；输出目录保留诊断信息，下次使用新的目录与新检出，不覆盖旧候选。编译日志中的本机路径只留在 native-build 目录，不加入安装包。

原生编译记录 C++/构建脚本摘要、编译器及 SDK 版本、DLL 摘要、签名状态和源码提交。完整回归使用 `--candidate-receipt`，在回归前后核对源码与 DLL，再生成绑定日志摘要的 regression.json；不接受旧源码回执、跳过测试或只有一句“通过”的文件。原生冒烟创建的是受控窗口，不代替真实产品 UI 验收；系统合成不可用时明确失败，不修改透明度偏好。

## 产物和复核

成功后输出 `codex-pulse-0.7.0-beta.12-windows.zip`。它包含新运行载荷、固定 beta.6 回退包、完整管理工具依赖、安装入口、候选说明、许可与待填的验收清单。默认安装到 `%LOCALAPPDATA%\CodexPulseCandidates\0.7.0-beta.12`，保护日常安装目录。

独立回读已经生成的 ZIP：

```powershell
python -X utf8 -B distribution/windows_candidate.py verify `
  --archive D:\PulseCandidates\beta12-run-01\codex-pulse-0.7.0-beta.12-windows.zip `
  --baseline D:\PulseInputs\codex-pulse-0.7.0-beta.10-windows.zip `
  --native-receipt D:\PulseCandidates\beta12-run-01\native-build\native-build.json `
  --smoke-receipt D:\PulseCandidates\beta12-run-01\native-smoke.json `
  --test-log D:\PulseCandidates\beta12-run-01\checks\unittest.log
```

需要同一干净源码和同一原生 DLL，test-log 同目录的 regression.json 也必须保留。检查外壳的完整文件集合和内容、内层运行载荷、源码提交、原生证据、恢复资产及包内文档；重算归档内的摘要不能掩盖多文件、漏文件或工具内容变更。完整 ZIP 的 SHA256 记入本机验收记录，不能把压缩包自身摘要放回自身形成循环引用。

接入已指定的 Windows 设备后按 [实机验收清单](ACCEPTANCE.md) 完成新装、运行中的公开 beta.10 升级、beta.6 回退、再升级，以及数据保留、失败恢复和真实窗口检查。当前这些结果全部待执行；构建成功也不会把 RESULTS.json 自动勾成通过。

本轮准备不创建 GitHub Release、发布标签或公开附件，不签名或公证，不构建 CLI。源码提交、候选构建、安装验收与公开发布继续按各自授权执行。
