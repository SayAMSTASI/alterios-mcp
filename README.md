# alterios-mcp

Готовый к эксплуатации MCP-сервер и набор инструментов инвентаризации для
экземпляров Alterios/LIMS.

Репозиторий развивается как полноценный операционный MCP, а не как узкий MVP.
Базовый контракт:

- Один MCP-профиль соответствует одному экземпляру Alterios: base URL, метод
  авторизации, токен, шаблон endpoint для скриптов и таймауты.
- Один экземпляр Alterios может содержать много проектов.
- Инструменты, завязанные на проект, принимают явный `project_id`. `project_id`
  из переменных окружения - только удобное значение по умолчанию, а не
  идентичность профиля.
- Инструменты уровня экземпляра, например инвентаризация проектов, не должны
  требовать `project_id`.
- Секреты читаются из переменных окружения или приватного dotenv-файла, не
  коммитятся в репозиторий и не возвращаются инструментами.

## Текущие Инструменты

- `alterios_config` - проверка профиля и конфигурации с редактированием
  секретов и списками недостающих значений.
- `alterios_list_profiles` - список настроенных экземпляров Alterios с
  редактированием секретов, выбранным профилем и missing-check по каждому
  профилю.
- `alterios_list_projects` - инвентаризация проектов на уровне экземпляра.
- `alterios_service_catalog` - каталог известных script-service функций с
  метками чтения/записи, уровнями риска, подсказками по аргументам и примерами.
- `alterios_call_readonly_service` - защищенные вызовы известных
  script-service функций только для чтения, например `getTasks`, `getContents` и `getViewData`,
  если настроен совместимый внешний сервисный endpoint.
- `alterios_rest_get` - безопасные REST-чтения по маршрутам `/api/...`.
- `alterios_list_objects` - инвентаризация типовых объектов Alterios через
  проверенные `listandcount` маршруты.
- `alterios_view_data_simplified` - проверочное чтение
  `/api/views/v2/get-data-simplified`.
- `alterios_report_full` - чтение полного отчета через кодированный маршрут
  `/api/reports/full/{filter}`.
- `alterios_get_view`, `alterios_view_entities` и
  `alterios_view_fields_populated` - чтение объекта представления, его
  join/entity-конфигурации и заполненных метаданных полей.
- `alterios_get_form` - чтение полной формы по ID.
- `alterios_list_fields` - инвентаризация полей типа контента с опциональными
  фильтрами `content_type_id` или `field_id`.
- `alterios_list_groups` - инвентаризация групп проекта через `/api/groups`.
- `alterios_file_metadata` - чтение метаданных файлов через `/api/file/list`.
- `alterios_list_comments` - инвентаризация комментариев через
  `/api/v1/comments`.
- `alterios_view_data` - чтение `/api/views/v2/get-data` с опциональным
  контекстом `content_id`, массивом `data_id` и `user_filters`.
- `alterios_discover_readonly` - живая матрица маршрутов только для чтения.
- `alterios_call_write_service` и `alterios_rest_write` - отключены, пока явно
  не выставлен `ALTERIOS_MCP_ALLOW_WRITE=1`; по умолчанию возвращают dry-run
  audit и не выполняют запись.
- `alterios_execute_manual_script` - запуск `/api/scripts/execute-manual` по
  UUID скрипта; также по умолчанию работает как dry-run и требует
  `ALTERIOS_MCP_ALLOW_WRITE=1` для выполнения.

Инструменты уровня проекта следует вызывать с `project_id`, когда целевой проект
известен из URL, UI-сессии или контекста задачи. Настроенный
`ALTERIOS_<PROFILE>_PROJECT_ID` - только значение по умолчанию для
повторяющейся работы с известным проектом.

## Установка

```powershell
git clone https://github.com/SayAMSTASI/alterios-mcp.git
cd alterios-mcp
python -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[dev]"
```

## Настройка Alterios

Используйте локальный приватный `.env`; не коммитьте его.

```powershell
Copy-Item .env.example .env
```

Пример профиля для одного экземпляра Alterios:

```dotenv
ALTERIOS_PROFILE=vniimt
ALTERIOS_PROFILES=vniimt,artx

ALTERIOS_VNIIMT_BASE_URL=http://lims.vniimt.local
ALTERIOS_VNIIMT_API_TOKEN=put-token-here

# Необязательное значение по умолчанию. Для инструментов уровня проекта лучше передавать project_id явно.
ALTERIOS_VNIIMT_PROJECT_ID=40466687-b093-4d80-b4f2-ba0ed0245bfa

ALTERIOS_VNIIMT_ENDPOINT_TEMPLATE={base_url}/api/scripts/execute-manual
ALTERIOS_VNIIMT_BODY_STYLE=manual_script
ALTERIOS_VNIIMT_AUTH_HEADER=x-api-key
ALTERIOS_VNIIMT_AUTH_SCHEME=
ALTERIOS_VNIIMT_TIMEOUT_SECONDS=20
```

Несколько экземпляров Alterios можно держать в одном приватном dotenv-файле.
Добавьте второй профиль с собственным префиксом:

```dotenv
ALTERIOS_ARTX_BASE_URL=https://alterios-artx.example.local
ALTERIOS_ARTX_API_TOKEN=put-token-here
ALTERIOS_ARTX_PROJECT_ID=put-optional-default-project-id-here
ALTERIOS_ARTX_ENDPOINT_TEMPLATE={base_url}/api/scripts/execute-manual
ALTERIOS_ARTX_BODY_STYLE=manual_script
ALTERIOS_ARTX_AUTH_HEADER=Authorization
ALTERIOS_ARTX_AUTH_SCHEME=Bearer
ALTERIOS_ARTX_TIMEOUT_SECONDS=20
```

Профили можно перечислить явно через `ALTERIOS_PROFILES` или оставить
автодетект по переменным вида `ALTERIOS_<PROFILE>_*`. Проверка всех настроенных
экземпляров без сетевых вызовов:

```powershell
python -m alterios_mcp.discovery --profiles --json
```

Чтобы посмотреть список профилей с другим выбранным экземпляром, не меняя
dotenv, передайте профиль явно:

```powershell
python -m alterios_mcp.discovery --profiles --profile artx --json
```

Для конкретного экземпляра используйте `--profile` в CLI или аргумент `profile`
в MCP tool-е. Для конкретного проекта внутри выбранного экземпляра передавайте
`project_id` явно.

`BASE_URL`, `API_TOKEN` и `PROJECT_ID` намеренно изолированы по профилю. Если
выбран профиль, сервер не делает скрытый переход на другой экземпляр или проект.
Профильные настройки транспорта (`AUTH_HEADER`, `AUTH_SCHEME`,
`ENDPOINT_TEMPLATE`, `BODY_STYLE`, `TIMEOUT_SECONDS`) также можно задавать с тем
же префиксом `ALTERIOS_<PROFILE>_...`; при их отсутствии применяются обычные
дефолты клиента или явно заданные общие значения.

Чтобы использовать уже существующую приватную конфигурацию и не копировать
секреты в этот репозиторий, задайте `ALTERIOS_DOTENV_PATH` вне репозитория:

```powershell
$env:ALTERIOS_DOTENV_PATH = "C:\Users\admin\Documents\AlteriosCodex\.env"
python -m alterios_mcp.discovery --profile vniimt --projects --json
```

В конфиг Codex MCP можно передать тот же путь к приватному dotenv:

```toml
[mcp_servers.alterios]
command = "C:\\path\\to\\alterios-mcp\\.venv\\Scripts\\python.exe"
args = ["-m", "alterios_mcp.server"]
startup_timeout_sec = 60
tool_timeout_sec = 120

[mcp_servers.alterios.env]
ALTERIOS_DOTENV_PATH = "C:\\Users\\admin\\Documents\\AlteriosCodex\\.env"
```

## Инвентаризация

Список проектов выбранного экземпляра Alterios:

```powershell
python -m alterios_mcp.discovery --profile vniimt --projects --json
```

Проверка конкретного проекта с явным `project_id`:

```powershell
python -m alterios_mcp.discovery --profile vniimt `
  --project-id 40466687-b093-4d80-b4f2-ba0ed0245bfa `
  --json
```

Сохранение воспроизводимого артефакта инвентаризации:

```powershell
New-Item -ItemType Directory -Force artifacts\alterios-mcp | Out-Null
python -m alterios_mcp.discovery --profile vniimt `
  --project-id 40466687-b093-4d80-b4f2-ba0ed0245bfa `
  --json > artifacts\alterios-mcp\live-readonly-matrix.json
```

Сканирование существующего репозитория Alterios-автоматизации на известные API
пути и кандидаты в script-service функции:

```powershell
python -m alterios_mcp.static_scan C:\Users\admin\Documents\AlteriosCodex `
  --json > artifacts\alterios-mcp\static-calls.json
```

Статический сканер по умолчанию пропускает сгенерированные и тяжелые рабочие
директории: `artifacts`, `data`, `outputs`, `site` и `work`. Используйте
`--include-generated` только когда нужно намеренное полное медленное
сканирование.

## Снятие Browser/UI Вызовов

Для снятия фактических вызовов из веб-интерфейса Alterios используйте
анализатор HAR/JSON-событий. Он не выполняет запросы к Alterios сам: только
читает сохраненный сетевой дамп, выкидывает не-API шум, редактирует секреты и
классифицирует маршруты по риску.

```powershell
python -m alterios_mcp.ui_flow .\capture.har `
  --profile vniimt `
  --project-id 40466687-b093-4d80-b4f2-ba0ed0245bfa `
  --scenario content-form-open `
  --json > artifacts\alterios-mcp\ui-flow-content-form-open.json
```

Команда доступна и как console script:

```powershell
alterios-ui-flow .\capture.har --scenario content-form-open --json
```

Неизвестные `POST`, `PUT`, `PATCH` и `DELETE` маршруты считаются write-like и
попадают в write-gate. Известные read-only исключения, например
`POST /api/views/v2/get-data`, описаны явно. Подробный workflow и правила
редактирования артефактов описаны в
[docs/browser-ui-discovery.md](docs/browser-ui-discovery.md).

## Запуск MCP-Сервера

```powershell
python -m alterios_mcp.server
```

Включайте режим записи только для проверенного безопасного профиля и проекта:

```powershell
$env:ALTERIOS_MCP_ALLOW_WRITE = "1"
```

Перед вызовами, которые могут менять состояние, запустите `alterios_config`,
проверьте выбранный профиль и передайте `project_id` явно. Поэтапный рабочий
план описан в [docs/roadmap.md](docs/roadmap.md), стратегия
инвентаризации - в
[docs/discovery-plan.md](docs/discovery-plan.md).

Политика controlled writes описана в
[docs/controlled-writes.md](docs/controlled-writes.md). Для реального выполнения
write-capable tool-а нужно одновременно:

- передать явные `profile` и `project_id`;
- включить `ALTERIOS_MCP_ALLOW_WRITE=1`;
- передать `dry_run=false`;
- для destructive операций дополнительно передать `allow_destructive=true`.

Управление проектом ведется в [docs/project-status.md](docs/project-status.md).
Правила мультиагентной работы и контрольные точки PM описаны в
[docs/project-management.md](docs/project-management.md). Каталог runtime-сервисов
скриптов описан в
[docs/script-runtime-catalog.md](docs/script-runtime-catalog.md).
Карта сущностей Alterios, возможных обращений, настроек и порядка write-практики
описана в [docs/alterios-entity-surface-catalog.md](docs/alterios-entity-surface-catalog.md).

## Practice-Сценарии

Для тестового ART X проекта есть воспроизводимый сценарий metadata chain:
создать или проверить sandbox content type и representative fields. По
умолчанию команда работает как dry-run:

```powershell
$env:ALTERIOS_DOTENV_PATH = "C:\Users\admin\Documents\AlteriosCodex\.env"
$env:PYTHONPATH = "src"
python scripts\artx_practice_metadata.py `
  --profile artx `
  --project-id 4e247a6b-55ef-4665-b88c-3c156fee19ba `
  --json
```

Для выполнения записи нужен явный write-gate:

```powershell
$env:ALTERIOS_MCP_ALLOW_WRITE = "1"
python scripts\artx_practice_metadata.py `
  --profile artx `
  --project-id 4e247a6b-55ef-4665-b88c-3c156fee19ba `
  --execute `
  --json
```

Важно: `/api/scripts/execute-manual` выполняет сохраненные Alterios-скрипты по
UUID. Этот endpoint не вызывает имена runtime-сервисов вроде `getTasks`.
Имена runtime-сервисов остаются в каталоге до тех пор, пока совместимый внешний
сервисный endpoint не будет настроен и проверен.

## Проверка

```powershell
python -m pytest
```
