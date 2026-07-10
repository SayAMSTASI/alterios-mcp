---
name: alterios-safety-verifier
description: Verify Alterios MCP safety before declaring work done. Use when checking profile/project targeting, secret redaction, dry-run behavior, write gates, destructive-operation gates, tests, git diff checks, generated artifacts, live readback, UI/HAR evidence, or residual risks after Alterios code, tools, docs, reports, forms, scripts, or skills change.
---

# Alterios Safety Verifier

Use this skill as an independent verification pass before marking an Alterios MCP change as done.

## Verification Checklist

1. Confirm the intended `profile` and `project_id`; do not rely on defaults for writes.
2. Run the relevant tests or targeted smoke checks.
3. Run `git diff --check`.
4. Scan changed files and generated artifacts for secrets.
5. For write tools, prove dry-run blocks by default and live write requires `ALTERIOS_MCP_ALLOW_WRITE=1`.
6. For live writes, check API readback; for user-facing surfaces, check UI or render evidence.
7. Record residual risks rather than hiding them.

For report/write changes, include targeted coverage from `tests/test_write_control.py` and `tests/test_stimulsoft_layout.py` unless a narrower command is explicitly justified.

## Secret Redaction

Never print or commit tokens, cookies, auth headers, passwords, API keys, private dotenv contents, or raw request headers containing credentials.

## References

Read `references/source-map.md` to select the correct safety evidence for the change type.
