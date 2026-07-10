# Repo-Owned Skills Installation

The repository keeps its project skills under `skills/`. To make them available
to Codex as local/global skills, install them into `$CODEX_HOME/skills` or
`~/.codex/skills`.

## Dry Run

```powershell
.\.venv\Scripts\python scripts\install_repo_skills.py --json
```

The command reports `install`, `skip`, or `replace` for each skill and does not
copy files unless `--execute` is passed.

## Install

```powershell
.\.venv\Scripts\python scripts\install_repo_skills.py --execute --json
```

If a target skill already exists, the installer skips it. Use `--replace` only
when the repo copy should overwrite the installed copy:

```powershell
.\.venv\Scripts\python scripts\install_repo_skills.py --replace --execute --json
```

## Path Handling

When skills are copied out of the repo, `references/source-map.md` is rewritten
to absolute paths pointing back to this repository. This keeps references to
`docs/`, `src/`, and `tests/` valid after installation.

## Validation

```powershell
Get-ChildItem -Directory C:\Users\admin\.codex\skills\alterios-* |
  ForEach-Object {
    .\.venv\Scripts\python C:\Users\admin\.codex\skills\.system\skill-creator\scripts\quick_validate.py $_.FullName
  }
```

After installation, start a new Codex session to load the newly installed skills
into the available-skill list.
