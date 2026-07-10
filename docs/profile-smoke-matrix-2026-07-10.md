# Profile Smoke Matrix

- Generated at: `2026-07-10T09:30:23+00:00`
- Read-only run: `True`
- Write gate enabled in environment: `False`
- Project IDs included: `False`
- Project names included: `False`

## Summary

| Metric | Value |
|---|---:|
| Profiles total | 2 |
| Instance project lists OK | 2 |
| Default project discovery OK | 2 |
| Default project discovery skipped | 0 |
| Projects discovered total | 53 |

## Profiles

| Profile | Token | Base URL | Default project | Projects | Default route smoke |
|---|---|---|---|---:|---|
| artx | <set> | <set> | <set> | 35 | 15/15 OK |
| vniimt | <set> | <set> | <set> | 18 | 15/15 OK |

## Failures And Skips

- No failed checks. Some project-scoped discovery may still be skipped when a profile has no default project id.

## Notes

- This runner calls only read-only inventory routes.
- Tokens, auth headers, private dotenv contents, and base URLs are not written to this artifact.
- Project IDs and names are omitted unless the runner is called with `--include-project-ids` or `--include-project-names`.
