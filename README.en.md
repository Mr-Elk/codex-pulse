# Codex Pulse

[简体中文](README.md) | English

A local usage strip for Codex on Windows. See token totals, estimated average TPS, cache hit rate, estimated context usage, and turn/request counts for your current conversation.

**Current version: 0.6.18-beta.5 · Pre-release.** Primarily tested on Windows 11 x64. Requires Python 3.10+ with Tkinter and Windows PowerShell. No API key or third-party Python packages are required at runtime.

The application UI is currently in Chinese. UI language switching is planned; this English README covers setup, controls, metrics, and limitations.

![Example usage strip](https://github.com/Mr-Elk/codex-pulse/releases/download/v0.6.18-beta.5/toolbar.png)

## Download and run

1. Download `codex-pulse-0.6.18-beta.5-windows.zip` from [Releases](https://github.com/Mr-Elk/codex-pulse/releases).
2. Extract the entire ZIP into a regular folder. Double-click **安装内测版.cmd** (Install beta).
3. Open `%LOCALAPPDATA%/CodexPulseBeta` and double-click **启动统计条.cmd** (Start usage strip).
4. Open a local Codex work conversation. If automatic identification is unavailable, use the ellipsis → **会话** (Sessions) to choose and pin a conversation.

Use the Windows package for normal installation. GitHub's automatically generated Source code ZIP is for development and does not contain the precompiled backdrop DLL. If Python is missing, the installer stops with an explanation; it does not install software for you.

For upgrades, run the new installer with the same installation directory. Preferences live in a separate `data` directory and are preserved. **回退上一版.cmd** (Roll back previous version) restores the retained previous version. A modified version file blocks upgrade/rollback rather than being overwritten. The first installation has no previous version to restore.

The installer does not enable login startup or change system execution policy. Close any existing strip before launching the standalone beta; the single-instance guard prevents overlapping instances. See the [Chinese beta guide](BETA_GUIDE.md) for additional details.

## Features and controls

- **Two presentations:** follow above the composer, or remain visible across applications as a desktop capsule. Click the left grip to switch; drag it to move.
- **Automatic or pinned statistics:** search unarchived local work sessions. Archived work is removed from the picker and returns after unarchiving.
- **Themes and text size:** twelve presets and an inline HEX/HSV editor. The strip, settings, and scroll thumbs share the selected theme.
- **SVG and glass:** consistent icons, rounded geometry, white contours, and antialiased rendering. A translucent fallback remains available when live blur is unsupported.
- **Quiet scrolling:** thumbs appear outside the content while scrolling, expand on hover/drag, then fade at rest. Content width stays fixed.
- **Local operation:** reads local records without making model requests, uploading conversations, or modifying the Codex installation.

Open settings with the right ellipsis or a right-click. **统计条** (Strip) controls metrics and text size; **显示** (Display) controls presentation and color; **会话** (Sessions) selects automatic or pinned tracking. Escape or the top-right × closes settings. **关闭统计条** at the bottom exits the entire companion.

![Display settings example](https://github.com/Mr-Elk/codex-pulse/releases/download/v0.6.18-beta.5/settings-display.png)

## Metrics and supported data

| Metric | Meaning |
|---|---|
| TPS | Estimated output tokens divided by the elapsed time of the latest completed request, including network and first-token waiting. Previous speed is not reused while generating. |
| Tokens | Cumulative input and output. Input includes repeatedly sent context; reasoning is already included in output. |
| Cache | Cached input divided by total input for the latest request. |
| Context | Latest request input plus output divided by the recorded context window; an estimate. |
| Turns / requests | Cumulative backend task runs / model requests. Turns are not necessarily user-message pairs. |

Automatic following matches the accessible navigation title to local display names and accepts only a unique match. Ambiguous or unavailable identity clears previous numbers; you can pin a session manually. Only local conversations with retained JSONL usage records are supported. Cloud-only history and data on other computers cannot be recovered. Unavailable data does not mean zero usage.

Codex Pulse is an independent Windows companion window, not a native composer extension or an official OpenAI product. Codex updates may change local record formats or accessibility structure.

## Validation and remaining beta work

See [VALIDATION.md](VALIDATION.md) for the measured scope. Controlled regressions are recorded separately from field acceptance. Real interruption/new-message prompts, prolonged use, other computers, multiple monitors, and mixed DPI remain beta checks.

UI language switching, clearer unavailable-data diagnostics, and large-catalog performance measurements remain on the [roadmap](TODO.md).

## Run from source

On Windows, clone the repository, enter its directory, and run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\launch.ps1
```

This execution-policy argument applies to that process only. Follow your organization's requirements if policy prevents execution.

Compiled artifacts are excluded from source control. To rebuild the optional live-backdrop DLL, use an existing Visual Studio C++ x64 Build Tools installation and Windows SDK:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\build_native.ps1
```

Without the DLL, the translucent surface still works. The Windows release package includes the x64 DLL.

Run the tests in an interactive Windows desktop session:

```powershell
python -X utf8 -B -m unittest discover -q
```

Tests use controlled Tk windows and temporary directories. They do not establish real Codex interruption or mixed-monitor acceptance. Development notes are in [CONTRIBUTING.md](CONTRIBUTING.md), and design decisions are in [DESIGN.md](DESIGN.md).

## Related projects

- [codex-statusbar](https://github.com/dongyue-19/codex-statusbar): a Windows Codex toolbar strip for TPS, tokens, and cache.
- [codex-monitor-hud](https://github.com/LH-03/codex-monitor-hud): a Windows multi-task HUD for Codex Desktop and CLI.
- [CodexBar](https://github.com/steipete/CodexBar): provider limits and reset monitoring, including macOS and Linux desktop interfaces.
- [ccusage](https://github.com/ccusage/ccusage): local CLI usage and estimated-cost analysis across coding agents.

These are independent projects. Their metric definitions and integration methods may differ; this list does not imply compatibility or integration.

## Feedback and license

Use [Issues](https://github.com/Mr-Elk/codex-pulse/issues) with the version, Windows scaling, presentation mode, and reproduction steps. Logs stay local. Remove private paths, conversation titles, UUIDs, and message content before sharing.

Licensed under [MIT](LICENSE).
