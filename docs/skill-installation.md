# Установка repo-owned skills

Репозиторий хранит проектные skills в папке `skills/`. Чтобы они стали
доступны Codex как local/global skills, установите их в `$CODEX_HOME/skills`
или `~/.codex/skills`.

## Dry-run

```powershell
.\.venv\Scripts\python scripts\install_repo_skills.py --json
```

Команда показывает `install`, `skip` или `replace` для каждого skill и ничего
не копирует, пока не передан `--execute`.

## Установка

```powershell
.\.venv\Scripts\python scripts\install_repo_skills.py --execute --json
```

Если target skill уже существует, installer его пропускает. Используйте
`--replace` только когда repo copy должна перезаписать установленную версию:

```powershell
.\.venv\Scripts\python scripts\install_repo_skills.py --replace --execute --json
```

## Обработка путей

При копировании skills из репозитория `references/source-map.md`
переписывается на абсолютные пути обратно в этот репозиторий. Так ссылки на
`docs/`, `src/` и `tests/` остаются рабочими после установки.

## Проверка

```powershell
Get-ChildItem -Directory "$env:USERPROFILE\.codex\skills\alterios-*" |
  ForEach-Object {
    .\.venv\Scripts\python "$env:USERPROFILE\.codex\skills\.system\skill-creator\scripts\quick_validate.py" $_.FullName
  }
```

После установки откройте новую Codex-сессию, чтобы newly installed skills
появились в списке доступных skills.
