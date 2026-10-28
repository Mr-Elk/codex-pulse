# Codex Pulse

- Windows companion source uses Python/Tk and GDI+. Preserve current account, session, theme, metric and display preferences during local validation.
- For code, configuration, worker or test changes, follow `ENGINEERING.md` for module boundaries, real failure scenarios and recovery checks. Configuration consumers use `quota_config`; `quota_service` retains compatibility exports for existing callers.
- For commits, candidates and releases, follow `WORKFLOW.md` for scoped documentation updates, independent platform versions, environment preservation and source-to-artifact traceability. Use `CONTRIBUTING.md` for test commands; a PR merge does not itself authorize packaging or publication.
- For settings, menus, dialogs, hover cards and statistics-strip work, read `UI_RULES.html` and reuse `ui_tokens.py`. A new spacing or type exception must have a concrete content or interaction reason, recorded in that specification.
- Usage records show aggregated local snapshot deltas, not individual polls. See `quota_records.py`. Preserve the raw account value, missing-data states and independent local/account freshness. Never interpolate missing intervals or fabricate currency units.
- UI acceptance requires operating the real local instance and inspecting screenshots at the target scale. Tests alone do not establish visual acceptance. Compare before/after for changed surfaces; check disabled/selected/focus states and short-screen overflow when relevant.
- Required local checks for these surfaces are the UI regression group in `CONTRIBUTING.md`; that file also defines the full-regression scope. Preserve the real-instance and screenshot requirements above.
- Do not commit, push, package, publish or release without the user's explicit request for that action.
