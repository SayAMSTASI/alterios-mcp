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
- `instance_count`: количество логических MCP-серверов после группировки
  Windows launcher/python child;
- количество дубликатов MCP instances.

На Windows один нормальный MCP запуск может отображаться несколькими
OS-процессами: `alterios-mcp.exe` launcher и дочерний `python.exe`. Для live-gate
важен не сырой `process_count`, а `instance_count` и `duplicate_instance_count`.

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

## Быстрый live-preflight

Для обычной бизнесовой разработки запускайте MCP с
`ALTERIOS_MCP_TOOL_PROFILE=live`. Активный реестр проверяйте через
`alterios_tool_profile`; смена профиля требует перезапуска процесса.

Перед live-задачей запускайте один read-only gate. Он собирает runtime freshness,
дубликаты MCP instances, project health, replay smoke и наличие приватной
delivery evidence в единый результат `ready/blocked`:

```powershell
.\.venv\Scripts\python.exe -m alterios_mcp.live_task_preflight `
  --profile <profile> `
  --project-id <project-id> `
  --scenario-tool alterios_create_material_module `
  --work-item-ref <private-task-ref> `
  --agent-handoff-ref <private-handoff-ref> `
  --pretty
```

Для типового записывающего сценария используйте `alterios_fast_live_write`.
Он объединяет preflight и сценарный dry-run/apply, но сохраняет обязательную
двухфазность: первый вызов возвращает `plan_id`, второй применяет тот же план.
Полный replay smoke по умолчанию не повторяется на каждой операции; его нужно
запускать после обновления MCP или явно включать через `include_replay_smoke=true`.

Project health использует только свежий cache. Стандартный TTL равен 300
секундам и настраивается через `ALTERIOS_MCP_HEALTH_CACHE_TTL_SECONDS` либо
`health_cache_ttl_seconds`. Просроченный snapshot используется как база diff,
после чего выполняется live refresh.

## Правило для live-записи

Для сценарных write-tools `alterios_create_material_module`,
`alterios_create_report_tab` и `alterios_create_process_flow` перед apply нужен
успешный `alterios_live_task_preflight`:

- `stale=false`;
- `matches_expected=true`, если передан expected fingerprint;
- `duplicate_instance_count=0`;
- `ux_contract_version` соответствует активному `alterios_ux_contract`;
- `project_health` не содержит blockers;
- private Gitea issue существует и открыт;
- handoff-комментарии аналитика, исполнителя и тестировщика прошли
  `alterios_verify_delivery_evidence`.

Если эти условия не выполнены, сначала очистите runtime и только потом
повторяйте dry-run/apply.
