# Security Policy

## Supported Versions

Codex Pulse is a Windows beta. Security fixes are provided for the latest published
Windows build only.

| Version | Security-fix support |
| --- | --- |
| `0.7.0-beta.x` (latest Windows beta) | ✅ |
| `0.6.x` and older betas | ❌ |
| Source snapshots and unreleased previews | No release-support commitment; reports welcome |

The Windows build supports Windows 11 x64 and requires Python 3.10+ with Tkinter and
Windows PowerShell. Native macOS desktop and separate CLI status-line previews exist
as local development candidates; neither has been publicly released. See the
[support overview](README.en.md#codex-desktop-and-codex-cli-support) for availability
and verification limits, and [MACOS.md](MACOS.md) for the Mac plan in this checkout.

Release-support status does not determine whether a report is welcome. Please report
security or privacy problems in actively developed source and preview versions too,
including shared code. We may ask whether an older-version issue also affects current
source or the latest supported release. This does not promise backports or a response
deadline for unpublished or older versions.

## Reporting a Vulnerability

Please do not open a public issue with exploit details, secrets, session content, or
personal paths.

GitHub private vulnerability reporting is enabled for this repository. Please use:

[Report a vulnerability privately](https://github.com/Mr-Elk/codex-pulse/security/advisories/new)

If private reporting is unavailable, open a minimal public issue stating that you have
a security report and asking for a private channel. Do not include technical details in
that issue.

Please include:

- Codex Pulse version, distribution or source commit, and whether it is a local preview.
- Operating system and architecture; for Windows UI issues, include the Windows build,
  display scaling, and composer-following or desktop mode. For CLI issues, include the
  terminal, Python, GNU screen, and Codex CLI versions.
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

- Codex Pulse code, including the overlay, settings, rendering paths, and actively
  developed macOS and CLI previews when the affected source or candidate is available.
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

- Vulnerabilities solely in Codex, ChatGPT, the operating system, Python, Tkinter, or
  other third-party software. Unsafe integration or exposure caused by Pulse remains
  in scope.
- Issues requiring physical access, administrator compromise, or an already-compromised
  local account.
- Resource exhaustion caused solely by deliberately overloading your own application.
  Resource exhaustion triggered by attacker-controlled input crossing a Pulse trust
  boundary is not excluded solely because Pulse runs locally.
- Social engineering.

Codex Pulse is an independent project, not an OpenAI product. Please do not report Codex
Pulse issues to OpenAI.

## Security Design and Threat Model

The published Windows companion reads existing session and account data. The following
describes that implementation; an interactive CLI preview has additional operations
for the user's Codex session and is not restricted to the quota-reader allowlist.

- It does not require an API key and does not upload session data to a third party.
- It reads local Codex session JSONL files and `logs_2.sqlite` in read-only mode.
- Pulse reads Codex session and timing records under `%CODEX_HOME%` (default `~/.codex`)
  without modifying those records. Pulse settings, runtime state, and usage history
  have separate storage.
- Account quota is read through the local Codex app-server over stdio, using an
  allowlist limited to `initialize`, `account/read`, and `account/rateLimits/read`.
  The Pulse quota reader does not directly open authentication files or start a model
  turn. The official Codex child process manages its own authentication and runtime
  state and may contact official services to obtain account quota. This feature is not
  fully offline, and read-only quota requests are not a promise that the child process
  makes no local writes.
- Its UI Automation probe reads window and control labels and rectangles. It does not
  read draft text, message bodies, or `ValuePattern`/`TextPattern` content.
- The optional source HTTP status surface binds to loopback and checks Host, Origin
  when supplied, and cross-site browser request metadata. These browser checks alone
  are not authentication of other local processes or operating-system users.
- It does not modify Codex installation files, install a service, or add auto-start.
  Settings, runtime state, and logs remain local, normally under the user's profile or
  an explicitly selected installation/data directory.
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
