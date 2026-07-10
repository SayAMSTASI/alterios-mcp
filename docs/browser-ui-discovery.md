# Обнаружение UI/HAR-сценариев Alterios

Этап 5 фиксирует, как веб-интерфейс Alterios реально обращается к backend до
добавления новых typed write tools. Первый готовый слой - локальный анализатор
HAR или JSON-снимков сетевых вызовов. Это read-only инструмент: он сам не
открывает браузер, не вызывает Alterios и не выполняет запись.

## Команда

```powershell
python -m alterios_mcp.ui_flow .\capture.har `
  --profile vniimt `
  --project-id 40466687-b093-4d80-b4f2-ba0ed0245bfa `
  --scenario content-form-open `
  --json > artifacts\alterios-mcp\ui-flow-content-form-open.json
```

Установленный console entrypoint делает то же самое:

```powershell
alterios-ui-flow .\capture.har --scenario content-form-open --json
```

## Поддерживаемые входные данные

- browser HAR exports с `log.entries`;
- обычные JSON-списки событий с `method`, `url`, опциональными `headers`,
  `body`, `status` и `response_body`;
- один JSON-объект события для малых smoke-check.

В результат попадают только маршруты `/api/...`. Статические assets и другой
шум браузера считаются отброшенными non-API events.

## Контракт результата

Анализатор пишет один JSON-объект:

- `context` - профиль, project id, сценарий и путь к исходному файлу;
- `flows` - упорядоченные route evidence: method, path, query keys,
  sanitized URL, status, content type, classification, target id placeholders,
  форма request body и форма response;
- `summary` - число read route, write-gated route, неизвестных write-like
  route и успешных write-like route;
- `redaction_report` - счетчики скрытых headers, fields, query values,
  пропущенных bodies, отброшенных non-API events и стабильных placeholders.

Целевые идентификаторы заменяются на стабильные placeholders вида `<id:1>`,
чтобы сценарий оставался трассируемым без сохранения production ID.

## Правила классификации

Классификатор fail-closed для мутирующих HTTP-методов.

Подтвержденные read-only routes:

- `GET|POST /api/*/listandcount`;
- `GET /api/contents...`;
- `POST /api/views/v2/get-data`;
- `POST /api/views/v2/get-data-simplified`;
- `GET /api/file/list`;
- `GET /api/v1/comments`;
- generic `GET`, `HEAD` и `OPTIONS`.

Write-gated routes:

- `POST|PATCH|PUT /api/contents/save`;
- `POST /api/file/upload/field`;
- `POST /api/v1/comments`;
- `POST /api/scripts/execute-manual`;
- мутирующие маршруты `/api/tasks`, `/api/processes` и `/api/diagrams`;
- мутирующие admin/config routes под `/api/forms`, `/api/views`,
  `/api/scripts`, `/api/reports`, `/api/helps`, `/api/view-fields` и
  `/api/view-entities`;
- любой неизвестный `POST`, `PUT`, `PATCH` или `DELETE`.

`DELETE /api/tasks/complete` классифицируется как workflow side effect, а не
как обычное удаление, потому что он продвигает задачу или процесс оператора.

## Правила редактирования секретов

Анализатор удаляет или заменяет:

- `Authorization`, `Cookie`, `Set-Cookie`, `x-api-key` и proxy auth headers;
- query/body keys со словами token, password, secret, api key,
  authorization;
- UI content values: `fields`, comments, rich text, names, titles, filenames
  и свободный текст;
- multipart upload bodies.

Он сохраняет порядок route, method/path, имена query keys, структуру body,
форму response, status code, content type, classification и стабильные
placeholders.

## Обязательные сценарии

Каждый сценарий сначала снимается в scratch/test project:

1. Открыть список и форму content без сохранения.
2. Сохранить одну scratch content record и прочитать ее обратно.
3. Загрузить маленький тестовый файл через file field и прочитать metadata.
4. Добавить и удалить scratch comment.
5. Выполнить form action, который вызывает manual script в test context.
6. Завершить или маршрутизировать scratch workflow task с before/after
   readback по task/process.
7. Проверить disposable user create/delete только в sandbox, с immediate
   cleanup и API readback.
8. Проверить cross-project content type transfer только при наличии
   согласованного target sandbox project.

Raw HAR остается приватным. В репозиторий можно коммитить только sanitized
JSON, если он нужен как evidence. Для read-only scenarios
`successful_write_like_route_count` должен быть `0`; для write-сценария он
должен совпадать с заранее одобренным действием.

## Вход для typed write tool

Production-oriented typed write строится только по sanitized evidence и должен
содержать:

- preflight read целевого объекта;
- явные `profile` и `project_id`;
- content type и field allowlist;
- dry-run diff;
- controlled write gate;
- readback verification после выполнения.

Текущий in-app browser connector не отдает raw HAR/network stream напрямую.
Когда HAR недоступен, evidence фиксируется как UI-visible flow + route snippets
из frontend bundle + API readback. True HAR в таком случае нужно экспортировать
из DevTools или отдельного сетевого capture.
