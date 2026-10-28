# Security Policy

## Supported Versions

Codex Pulse is a Windows beta. Security fixes are provided for the latest published
Windows build only.

| Version | Supported |
| --- | --- |
| `0.7.0-beta.x` (latest Windows beta) | ✅ |
| `0.6.x` and older betas | ❌ |
| Source snapshots and unreleased branches | ❌ |

The Windows build supports Windows 11 x64 and requires Python 3.10+ with Tkinter and
Windows PowerShell. macOS has a shared Python backend but no native window or signed
build yet; see [MACOS.md](MACOS.md). A CLI front end for Linux and Windows terminals is
in development and is not covered by this policy until it is published.

## Reporting a Vulnerability

Please do not open a public issue with exploit details, secrets, session content, or
personal paths.

Preferred: use GitHub private vulnerability reporting, if it is enabled for this
repository:

https://github.com/Mr-Elk/codex-pulse/security/advisories/new

If private reporting is unavailable, open a minimal public issue stating that you have
a security report and asking for a private channel. Do not include technical details in
that issue.

Please include:

- Codex Pulse version and whether you use the Windows ZIP or the source launcher.
- Windows version and build, display scaling, and whether you use composer-following or
  desktop capsule mode.
- A short description of the issue and its impact.
- Minimal reproduction steps.
- Sanitized logs or screenshots, with session titles, UUIDs, user names, local paths,
  tokens, and message content removed.

Please do not include:

- API keys, tokens, cookies, credentials, or account identifiers.
- Full Codex session files, `logs_2.sqlite`, or message bodies.
- Screenshots or logs exposing personal conversations or file paths.
- Anything that identifies your Codex account beyond what is needed to reproduce.

## Scope

In scope:

- Codex Pulse Python code, including the overlay, settings, and rendering paths.
- PowerShell launch, install, upgrade, and rollback scripts, and the `.cmd` entry points.
- Release packaging, asset handling, and `SHA256SUMS.txt` verification.
- The optional native blur DLL (`native_backdrop.cpp`) and `build_native.ps1`.
- Local data handling under the Codex Pulse data directories, including settings,
  runtime state, and logs.
- The read-only local app-server bridge used for account quota, including its method
  allowlist and any place where a response could expose more than quota, reset, or
  usage data.
- UI Automation behavior that reads more than the documented window and composer
  metadata.

Out of scope:

- Vulnerabilities in Codex, ChatGPT, Windows, Python, Tkinter, or other third-party
  software.
- Issues requiring physical access, administrator compromise, or an already-compromised
  local account.
- Denial of service that only affects the local user's own session.
- Social engineering and reports against unsupported versions.

Codex Pulse is an independent project, not an OpenAI product. Please do not report Codex
Pulse issues to OpenAI.

## Security Design and Threat Model

Codex Pulse is designed as a local, read-only companion:

- It does not require an API key and does not upload session data to a third party.
- It reads local Codex session JSONL files and `logs_2.sqlite` in read-only mode.
- It reads `%CODEX_HOME%` (default `~/.codex`) and does not write to it.
- Account quota is read through the local Codex app-server over stdio, using an
  allowlist limited to `initialize`, `account/read`, and `account/rateLimits/read`.
  It never opens auth files and never starts a model turn.
- Its UI Automation probe reads window and control labels and rectangles. It does not
  read draft text, message bodies, or `ValuePattern`/`TextPattern` content.
- A local HTTP endpoint used for the status surface binds to loopback and rejects
  requests whose `Origin` is not the local page.
- It does not modify Codex installation files, install a service, or add auto-start.
  Settings, runtime state, and logs stay under the local user's profile.
- The Windows release contains a prebuilt x64 blur DLL. Its source and build script are
  in the repository. `SHA256SUMS.txt` is an integrity check, not a code signature.

If you find behavior that contradicts any of these statements, treat it as a security
or privacy report.

## Safe Harbor

Good-faith security research is welcome. Please:

- Test only on your own machine and your own data.
- Do not access, modify, or exfiltrate another person's data.
- Do not run destructive tests or attempt to bypass OS security boundaries.
- Give the maintainer a reasonable opportunity to fix the issue before public
  disclosure.

## Disclosure

This is a single-maintainer beta with no bug bounty and no formal SLA. Reports are
handled on a best-effort basis. Please coordinate disclosure with the maintainer and do
not publish exploit details while a fix is being prepared.

## Security Updates

Security-relevant changes are noted in release notes when appropriate. Run the latest
Windows beta and verify release assets against `SHA256SUMS.txt`.
