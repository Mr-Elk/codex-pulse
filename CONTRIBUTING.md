# 开发与测试

需要 Windows、Python 3.10+（含 Tkinter）和 PowerShell。核心代码仅用标准库与 Windows API；背景模糊的 C++ 构建工具是可选开发依赖。

```powershell
python -X utf8 -B -m unittest discover -q
```

测试创建受控 Tk 窗口和临时目录，请在可用的本地桌面会话运行。没有原生桌面的环境不算界面验收。若临时目录受保护，可将 TEMP/TMP 指向有写权限的本地目录。

界面修改请保留已确认的 SVG/Logo 几何、主题颜色同步、字体家族、固定统计身份和个人设置兼容性。覆盖用户行为与失败边界，不为单纯样式改动机械增加镜像测试。

发布文件使用 release_tools.py 生成并核对 SHA256，包含 LICENSE。DLL、PNG 导出、安装包、截图、缓存与本机数据不提交源码；预编译 DLL 和界面示例作为 Release 附件提供。

请勿在 Issue、提交或附件中包含个人设置、会话数据、原始日志、私有安装指针或凭据。使用示例数据复现问题。
