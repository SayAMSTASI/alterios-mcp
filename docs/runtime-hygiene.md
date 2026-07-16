# Runtime hygiene для Alterios MCP

Этот документ описывает быстрый контроль локального runtime перед live-задачами.
Цель - не допускать ситуацию, когда Codex видит один MCP, а на машине остаются
несколько старых `alterios-mcp` процессов с другой схемой tools.

## Когда запускать

Запускайте проверку:

- после перезапуска Codex;
- после изменения MCP code, skills или UX-контракта;
- перед live `dry-run -> apply`;
- если tool registry выглядит устаревшим или появляется `Transport closed`;
- если работа стала заметно медленнее.

## Проверить runtime

```powershell
.\.venv\Scripts\alterios-runtime-info.exe --processes --pretty
```

Команда возвращает:

- fingerprint исходников, skills и UX-контракта;
- PID и время старта текущего процесса;
- признак `stale`;
- список локальных процессов, похожих на `alterios-mcp`;
- количество дубликатов.

## Очистить старые процессы

Сначала dry-run:

```powershell
.\.venv\Scripts\alterios-runtime-info.exe --processes --cleanup-stale --keep-newest 1 --pretty
```

Применить очистку:

```powershell
.\.venv\Scripts\alterios-runtime-info.exe --processes --cleanup-stale --keep-newest 1 --apply --pretty
```

Если нужно полностью остановить MCP перед новым запуском:

```powershell
.\.venv\Scripts\alterios-runtime-info.exe --processes --cleanup-stale --keep-newest 0 --apply --pretty
```

После очистки перезапустите MCP/Codex и проверьте:

```powershell
.\.venv\Scripts\alterios-replay-smoke.exe --json
```

## Правило для live-записи

Для сценарных write-tools `alterios_create_material_module`,
`alterios_create_report_tab` и `alterios_create_process_flow` перед apply нужен
свежий `alterios_runtime_info`:

- `stale=false`;
- `matches_expected=true`, если передан expected fingerprint;
- `duplicate_process_count=0`;
- `ux_contract_version` соответствует активному `alterios_ux_contract`.

Если эти условия не выполнены, сначала очистите runtime и только потом
повторяйте dry-run/apply.
