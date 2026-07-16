# Профили MCP tools

`alterios-mcp` поддерживает несколько реестров инструментов. Профиль выбирается
до запуска процесса через `ALTERIOS_MCP_TOOL_PROFILE` и уменьшает объём схемы,
которую MCP-клиент загружает в контекст.

| Профиль | Назначение | Generic write |
|---|---|---|
| `live` | Обычная разработка Alterios: preflight, health, сценарные и необходимые typed tools | Нет |
| `discovery` | Инвентаризация, чтение, анализ и валидаторы без записи | Нет |
| `admin` | Discovery плюс административные, security и typed write tools | Нет |
| `full` | Полный реестр для разработки MCP и исследования неизвестных routes | Да |

По умолчанию библиотека сохраняет совместимость и использует `full`. Для
ежедневной работы рекомендуется явно задавать `live` в конфигурации MCP:

```toml
[mcp_servers.alterios.env]
ALTERIOS_MCP_TOOL_PROFILE = "live"
```

После изменения профиля процесс MCP необходимо перезапустить. Инструмент
`alterios_tool_profile` возвращает активный профиль, исходное и итоговое
количество tools, разрешённые группы и удалённые из реестра команды.

Профиль не является write-разрешением. Для live-записи по-прежнему нужны
`ALTERIOS_MCP_ALLOW_WRITE=1`, успешный `alterios_live_task_preflight`, проверенный
`plan_id`, совпадающий runtime fingerprint и readback.

`live`, `discovery` и `admin` не публикуют generic escape hatches
`alterios_rest_write` и `alterios_call_write_service`. Если повторяемая операция
требует один из них, сначала следует добавить или расширить typed tool.

## Проверка agent evidence

Live preflight по умолчанию, а сценарный apply всегда проверяют private Gitea
issue и структурированные handoff-комментарии. Список обязательных ролей задаётся через
`ALTERIOS_MCP_REQUIRED_AGENT_ROLES=analyst,implementer,verifier`.

Каждый принимаемый handoff должен содержать роль, scope, результат, артефакты,
проверку, риски и следующий шаг. Все handoff-ссылки должны относиться к той же
задаче, которая указана в `work_item_ref`.
