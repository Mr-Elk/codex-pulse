# Security Policy

## Supported Versions

Codex Pulse is a Windows-local beta. Security fixes are provided for the latest published beta only.

| Version | Supported |
| --- | --- |
| `0.6.18-beta.x` (latest) | ✅ |
| Older betas and source snapshots | ❌ |

The project targets Windows 11 x64. WSL/Linux is not supported.

## Reporting a Vulnerability

Please do not open a public issue with exploit details, secrets, session content, or personal paths.

Preferred: use GitHub's private vulnerability reporting, if it is enabled for this repository:

https://github.com/Mr-Elk/codex-pulse/security/advisories/new

If private reporting is unavailable, open a minimal public issue saying that you have a security report and asking for a private channel. Do not include technical details in that issue.

Please include:

- Codex Pulse version, and whether you use the Windows ZIP or the source launcher.
- Windows version/build and display or DPI setup.
- A short description of the issue and its impact.
- Minimal reproduction steps.
- Sanitized logs or screenshots. Remove session titles, UUIDs, user names, local paths, tokens, and message content.

Please do not include:

- API keys, tokens, cookies, or credentials.
- Full Codex session files or message bodies.
- Screenshots or logs that reveal personal conversations or file paths.

## Scope

In scope:

- The Codex Pulse Python code.
- PowerShell launch, install, upgrade, and rollback scripts.
- Release packaging and asset handling.
- The optional native blur DLL and its build script.
- Local data handling under `%LOCALAPPDATA%/CodexPulseBeta`, including settings, runtime state, and logs.
- UI Automation behavior that reads more than the documented window and composer metadata.

Out of scope:

- Vulnerabilities in Codex, ChatGPT, Windows, Python, Tkinter, or other third-party software.
- Issues that require physical access, administrator compromise, or an already-compromised local account.
- Denial of service that only affects the local user's own session.
- Social engineering.
- Reports against older beta versions that are no longer supported.

Codex Pulse is an independent project, not an OpenAI product. Please do not report Codex Pulse issues to OpenAI.

## Security Design and Threat Model

Codex Pulse is designed as a local, read-only companion:

- It does not call model APIs, require an API key, or upload session data.
- It reads local Codex JSONL session files and `logs_2.sqlite` in read-only mode.
- Its UI Automation probe reads window and control labels and rectangles. It is not intended to read draft text or message bodies.
- It does not modify Codex installation files, install a service, or add auto-start.
- Settings, runtime state, and logs stay under the local user's profile.
- The Windows release contains a prebuilt x64 blur DLL. The source and build script are in the repository. `SHA256SUMS.txt` is an integrity check, not a code signature.

If you find behavior that contradicts any of these statements, treat it as a security or privacy report.

## Safe Harbor

Good-faith security research is welcome. Please:

- Test only on your own machine and your own data.
- Do not access, modify, or exfiltrate another person's data.
- Do not run destructive tests or attempt to bypass OS security boundaries.
- Give the maintainer a reasonable opportunity to fix the issue before public disclosure.

## Disclosure

This is a single-maintainer beta project with no bug bounty and no formal SLA. Reports are handled on a best-effort basis. Please coordinate disclosure with the maintainer and do not publish exploit details while a fix is being prepared.

## Security Updates

Security-relevant changes will be noted in release notes when appropriate. Users should run the latest beta and verify release assets against `SHA256SUMS.txt`.
