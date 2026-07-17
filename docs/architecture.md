# Архитектура Alterios MCP

Актуально для версии 0.2.3. Текущий публичный registry: 108 tools; профили
`live`/`discovery`/`admin`/`full` содержат 81/55/106/108 tools соответственно.

## 1. Назначение

Архитектура разделяет MCP-регистрацию, бизнес-сценарии и переиспользуемые
примитивы. `server.py` является только точкой сборки FastMCP и не содержит
реализацию операций Alterios.

## 2. Слои

| Слой | Каталог | Ответственность |
|---|---|---|
| Composition root | `src/alterios_mcp/server.py` | Создание FastMCP, регистрация tools, применение профиля, запуск сервера; около 100 строк |
| Registration | `src/alterios_mcp/tools/` | Доменные списки tools и их регистрация без бизнес-логики |
| Scenarios | `src/alterios_mcp/scenarios/` | Чтение, планирование, запись, readback и составные workflow без зависимости от FastMCP |
| Builders | `src/alterios_mcp/builders/` | Чистое построение payload, write operations и UI-фрагментов |
| Validators | `src/alterios_mcp/validators/` | Чистые проверки конфигураций, типов и ожидаемых сущностей |
| Shared support | `src/alterios_mcp/_support.py` | Общие клиенты, поиск ресурсов и совместимые внутренние helpers |

## 3. Домены регистрации

Регистрация разделена на 12 доменов:

1. `runtime`;
2. `workboard`;
3. `write_audit`;
4. `discovery`;
5. `icons`;
6. `security`;
7. `content`;
8. `views_forms`;
9. `processes`;
10. `reports`;
11. `live`;
12. `diagnostics`.

Каждый модуль `tools/<domain>.py` содержит только `TOOL_NAMES`, получение
scenario callables и функцию `register`. MCP-схема строится из сигнатуры
соответствующей функции в `scenarios/<domain>.py`.

## 4. Совместимость

Golden snapshot находится в
`tests/fixtures/tool_registry_snapshot.json` и фиксирует:

- 108 публичных имён tools;
- JSON Schema аргументов каждого tool;
- состав профилей `full`, `live`, `discovery`, `admin`.

`server.py` временно сохраняет Python-level re-export и compatibility bridge
для старых unit-тестов и внешних импортов `alterios_mcp.server.<tool>`. MCP
регистрирует непосредственно FastMCP-независимые scenario functions.

## 5. Правила развития

1. Новая бизнес-операция создаётся в подходящем `scenarios/` модуле.
2. Payload builder или validator выносится в соответствующий независимый слой.
3. В `tools/<domain>.py` добавляется только имя нового callable.
4. Изменение публичной сигнатуры требует осознанного обновления golden snapshot.
5. `server.py` должен оставаться меньше 500 строк.
6. `tools/` не должен содержать бизнес-логику.
7. `scenarios/`, `builders/` и `validators/` не импортируют FastMCP или `server.py`.
8. После изменения запускаются registry snapshot, replay smoke, полный pytest и public-tree scan.

## 6. Lazy imports

Lazy imports не используются на первом этапе. Сначала сохраняются прозрачная
регистрация и диагностируемый import graph. Отложенную загрузку можно добавлять
только после замера startup time и при сохранении golden snapshot и replay smoke.
