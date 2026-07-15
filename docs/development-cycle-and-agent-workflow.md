# Положение о цикле разработки и работе агентов

Этот документ задает рабочий порядок для разработки `alterios-mcp`, настройки
Alterios-проектов через MCP и командной работы агентов. Цель положения -
ускорить разработку без потери проверяемости: каждая задача должна заканчиваться
рабочим результатом, понятной проверкой и решением, что попадает в Git.

## 1. Область применения

Положение применяется к четырем типам работ:

1. Разработка MCP: tools, CLI, tests, validators, сценарные команды.
2. Развитие skills и агентов: правила, роли, handoff, reusable playbooks.
3. Live-настройка Alterios: материалы, поля, представления, формы, скрипты,
   BPMN, отчеты, иконки, пользователи и роли.
4. Документация: README, инструкции администратора/пользователя, постановки,
   ГОСТ-ориентированные материалы и внутренние регламенты.

Если задача относится только к конкретному бизнес-проекту Alterios, в Git
попадают только обезличенные reusable-улучшения. Реальные URL, project id,
материалы, пользователи, HAR, screenshots, write-journal и сырые выгрузки
остаются локально или в закрытом хранилище.

## 2. Базовый цикл

Любая нетривиальная задача проходит один и тот же цикл:

```text
Запрос -> Постановка -> Декомпозиция -> Реализация -> Проверка -> Документация -> Git-решение -> Закрытие
```

Короткая версия цикла:

1. Понять цель, контекст, профиль Alterios и ожидаемый результат.
2. Сформулировать минимальную постановку и acceptance criteria.
3. Разделить работу по ролям агентов и зонам ответственности.
4. Сделать самый ценный рабочий slice.
5. Проверить результат тестами, readback, smoke или UI evidence.
6. Зафиксировать изменения в документации или статусе.
7. Решить, что пушится в Git, а что остается локально.
8. Закрыть задачу кратким отчетом и следующим шагом.

## 3. Типы задач

| Тип задачи | Где выполняется | Что считается результатом | Git |
|---|---|---|---|
| MCP/tooling | Репозиторий `alterios-mcp` | Код, тесты, docs, smoke | Пушим |
| Skill/agent | `skills/`, `docs/` | Обновленный skill/agent/playbook | Пушим |
| Business live-write | Конкретный Alterios-проект | Изменения в UI/API, readback, UI evidence | Не пушим внутренности |
| Business -> reusable improvement | Alterios + repo | Обезличенное правило, validator, tool или skill | Пушим только reusable |
| Документация пользователя/админа | `docs/` или отдельный artifact | Проверенный документ | Пушим, если без чувствительных данных |
| Исследование | Локальные artifacts, docs при обезличивании | Матрица, выводы, gaps | Пушим только обезличенное |

## 4. Роли агентов

### Lead Engineer

Владелец результата. Интегрирует работу агентов, принимает технические решения,
проверяет итог, коммитит и пушит. Не делегирует ответственность за финальное
качество.

### PM Control Loop

Держит этап, acceptance criteria, риски, блокеры и следующий шаг. Обновляет
статус после каждого проверенного slice.

### Business/System Analyst

Переводит бизнес-запрос в постановку или ТРЗ: цель, роли, сценарии, сущности,
поля, формы, представления, скрипты, BPMN, отчеты, ограничения и критерии
приемки.

### Project Base Explorer

Работает read-only. Собирает project base: content types, fields, views, forms,
scripts, diagrams, reports, files, groups, users/roles, route shapes и gaps.

### Data Model Engineer

Проектирует типы материалов, поля, связи, справочники, публикацию типов
материалов и правила миграции данных.

### View Builder

Проектирует представления, experimental/classic режимы, view entities, joins,
view fields, filters, sorts, source fields и readback через `get-data`.

### Form Surface Engineer

Проектирует формы: tabs, rows, cells, `field`, `view_data`, `view_data_list`,
reports, comments, actions, F-pattern, пустые места, заголовки, роли, стили,
`openId/dataId` и field-based filters.

### UI Icons & Actions Reviewer

Проверяет иконки, iconId, порядок действий, меню, tooltip, Google Fonts Icons,
цвет `#4B77D1`, размер из утвержденного стандарта и смысл действия.

### Script/BPMN Flow Integrator

Картирует scripts, form actions, args, BPMN, listeners, service tasks, userTask
forms, process start/task complete и side effects.

### Report/Stimulsoft Specialist

Отвечает за Project Database datasource, report tabs, `openId`, Stimulsoft
template, printable layout, dashboard analytics, PDF/render risks.

### Write Tool Engineer

Превращает повторяемый live-flow в typed MCP tool: schema, dry-run, `plan_id`,
write gate, readback, tests, docs.

### Safety Verifier

Проверяет профиль, project id, write gates, dry-run/apply, redaction, tests,
git diff, sensitive scan, readback и UI evidence.

### Documentation Scribe / Писарь

Оформляет инструкции, администраторскую документацию, пользовательские сценарии
и ГОСТ/ЕСПД-ориентированные материалы на основе проверенных фактов.

## 5. Правила взаимодействия агентов

Главный агент не раздает общую задачу целиком. Каждый subagent получает узкую
зону ответственности и конкретный ожидаемый output.

Формат задания агенту:

```text
Роль:
Контекст:
Зона ответственности:
Что нельзя менять:
Ожидаемый output:
Проверка:
Срок/граница:
```

Формат ответа агента:

```text
Роль:
Scope:
Inputs:
Findings:
Artifacts:
Проверка:
Риски:
Дальше:
```

Правила:

- не дублировать одну и ту же работу между агентами;
- не давать агенту live-write без явного gate;
- не считать мнение агента проверкой без команды, readback или UI evidence;
- при конфликте выводов Lead Engineer принимает решение и фиксирует причину;
- QA/Safety agent должен проверять уже собранный slice, а не заменять
  реализацию.

## 6. Stage gates

### Gate 1. Intake

Вход принят, если понятно:

- какой профиль/проект/репозиторий затрагивается;
- что должно измениться для пользователя;
- какие ограничения уже известны;
- нужна ли live-запись;
- нужно ли пушить reusable-изменения.

### Gate 2. Постановка

Постановка готова, если есть:

- цель;
- пользовательские сценарии;
- сущности и поля;
- views/forms/scripts/BPMN/reports, если применимо;
- acceptance criteria;
- open questions или принятые допущения.

### Gate 3. План реализации

План готов, если определены:

- роли агентов;
- файлы/объекты Alterios, которые можно менять;
- read-only discovery;
- write strategy;
- проверки;
- rollback/cleanup notes для live-write.

### Gate 4. Dry-run

Для write-like действий dry-run обязателен, если tool поддерживает его. Dry-run
считается готовым, если есть:

- `plan_id`, когда применимо;
- diff или planned payload;
- target ids;
- профиль и project id;
- оценка риска;
- отсутствие blocking health errors.

### Gate 5. Apply

Live apply разрешен, если:

- профиль и project id проверены;
- `ALTERIOS_MCP_ALLOW_WRITE=1` включен осознанно;
- destructive/security write имеет отдельный gate;
- dry-run план проверен;
- понятно, как сделать readback;
- нет нерешенного риска, который может сломать проект.

### Gate 6. Verification

Результат verified только после одной или нескольких проверок:

- unit tests;
- CLI smoke;
- API readback;
- UI evidence;
- HAR/route evidence;
- report render/layout validation;
- sensitive scan;
- `git diff --check`.

### Gate 7. Closeout

Задача закрыта, если есть:

- краткое описание результата;
- список измененных файлов или live-объектов;
- что проверено;
- что не проверено;
- остаточные риски;
- commit hash, если был push;
- следующий шаг.

## 7. Definition of Done

### Для MCP/tooling

- код реализован минимально достаточным способом;
- есть tests на happy path и error path;
- write-like tool имеет dry-run по умолчанию;
- sensitive fields редактируются;
- docs/README/skill обновлены, если меняется пользовательское поведение;
- `pytest` или targeted tests прошли;
- `git diff --check` прошел;
- нет чувствительных данных в diff.

### Для Alterios live-задачи

- выбран явный `profile` и `project_id`;
- перед live-записью выполнен health/preflight, если задача меняет структуру;
- создан dry-run или письменный план изменений;
- apply выполнен только после gate;
- сделан readback;
- для UI-facing изменений есть UI evidence;
- реальные данные проекта не добавлены в Git.

### Для формы

- форма имеет правильный тип: list/add/edit/detail/task/main;
- заголовок человекочитаемый;
- нет необоснованных пустых мест;
- embedded views имеют фильтр по полю или `dataId/openId`;
- `view_data_list` с таблицей имеет центрированный bold заголовок ячейки;
- нет заголовка ячейки для нетабличного отображения;
- действия страницы и элементов соответствуют стандарту иконок;
- проверена навигация между list/view/edit/add.

### Для представления

- режим выбран осознанно: experimental/v2 по умолчанию, classic только при
  подтвержденной необходимости;
- fields добавлены через view fields, а не только в content type;
- связи проверены relation field или entity chain;
- технические и неинформативные столбцы скрыты;
- `get-data` или UI preview показывает ожидаемые строки.

### Для скриптов/BPMN

- тип script определен: web/cron/manual/event/library/diagram;
- args описаны;
- library links через `librariesIds` проверены;
- web/cron не активируются без явного решения;
- BPMN refs, listeners, `camunda:formKey` и side effects закартированы;
- manual/process/task smoke выполнен, если меняется runtime behavior.

### Для отчетов

- источник данных подтвержден;
- `openId/dataId` проверен для current-record отчетов;
- Stimulsoft layout проверен на overlap/overflow/dynamic height risks;
- аналитические и печатные формы открываются в новой вкладке;
- есть действие страницы `Закрыть`;
- viewer/render проверен, если это часть acceptance.

## 8. Git-решение

Пушим:

- MCP code, tests, validators;
- README и обезличенные docs;
- reusable skills/agents/playbooks;
- обобщенные правила, полученные из business-задачи;
- synthetic examples без live project data.

Не пушим:

- реальные project ids и URL контуров;
- пользовательские данные, email, tokens, role bindings;
- raw HAR/screenshots/video;
- write-plans/write-journal;
- inventory snapshots с внутренними названиями;
- постановки конкретного клиента, если они содержат внутренний контекст.

Если задача смешанная, Git получает только универсальный результат. Live evidence
остается локально или обезличивается.

## 9. Стандартный отчет после работы

Финальный ответ должен быть коротким и проверяемым:

```text
Готово.

Изменено:
- ...

Проверено:
- команда / readback / UI evidence

Git:
- commit hash / не пушилось, причина

Осталось:
- ...
```

Если проверка не выполнена, это указывается явно.

## 10. PM-таблица статуса

Для крупных задач PM ведет таблицу:

| Stage | Статус | Ответственный | Артефакт | Проверка | Риск | Следующий шаг |
|---|---|---|---|---|---|---|
| Intake | todo/in progress/done | PM | Постановка | Review | ... | ... |
| Discovery | todo/in progress/done | Explorer | Inventory | Read-only commands | ... | ... |
| Design | todo/in progress/done | Analyst/Architect | Spec | Review | ... | ... |
| Build | todo/in progress/done | Engineer | Patch/live config | Tests/readback | ... | ... |
| Verify | todo/in progress/done | Safety | Evidence | Smoke/UI/tests | ... | ... |
| Docs/Git | todo/in progress/done | Lead/Scribe | Docs/commit | Sensitive scan | ... | ... |

Статус `done` нельзя ставить без артефакта и проверки.

## 11. Практический режим ускорения

Чтобы быстрее пилить функционал, приоритет отдается сценарным tools и
повторяемым командам:

- `alterios_project_health` перед live structural write;
- `alterios_create_material_module` для типового модуля материалов;
- `alterios_create_report_tab` для report tab;
- `alterios_create_process_flow` для BPMN/process flow;
- `alterios_form_surface_check` для форм;
- `alterios_validate_stimulsoft_layout` для отчетов;
- `alterios_replay_smoke` после обновления MCP;
- typed write tools вместо ручного generic REST, если workflow повторяется.

Если действие повторяется второй раз, его нужно рассмотреть как кандидата на
tool, helper script, validator или skill update.

## 12. Запреты

- Не выполнять destructive/security live-write без отдельного gate.
- Не менять чужой live script без предварительного описания риска и плана.
- Не считать JSON save достаточной проверкой пользовательской формы.
- Не переносить `iconId` между проектами.
- Не использовать сырой HAR/screenshot как Git-документ без обезличивания.
- Не создавать новый skill на непроверенной гипотезе.
- Не смешивать бизнесовый контекст клиента с reusable MCP-документацией.
