# План оптимизации Alterios MCP

Дата: 2026-07-10

Цель: перейти от набора отдельных typed calls к сценарному контуру, где Codex
может планировать, применять, проверять и объяснять изменения в Alterios.

## Этап 15. Write workflow foundation

Статус: выполнен.

Что входит:

1. `plan_id` для dry-run write tools.
2. Хранение dry-run планов в `artifacts/write-plans/<profile>/<project_id>/`.
3. Журналирование планов и execution events в
   `artifacts/write-journal/<profile>/<project_id>/`.
4. MCP tools для просмотра:
   - `alterios_list_write_plans`;
   - `alterios_get_write_plan`;
   - `alterios_write_journal`.
5. Первый enforcing path: `alterios_rest_write` при `dry_run=false` требует
   `plan_id` и сверяет target/operation с сохраненным dry-run.

Критерии приемки:

- dry-run возвращает `plan.plan_id`;
- plan JSON не содержит секретов;
- apply generic REST write без `plan_id` блокируется;
- apply с измененным payload по старому `plan_id` блокируется;
- execution пишет journal entry;
- тесты и secret scan проходят.

## Этап 16. Сценарные tools

Цель: заменить ручные цепочки мелких calls на сценарные операции.

### `alterios_create_material_module`

Статус: реализован первым сценарным write-tool.

Сценарий:

1. content type;
2. fields;
3. view;
4. view entity;
5. view fields;
6. add/edit/list forms;
7. menu group;
8. readback через view data и form readback.

Критерии:

- dry-run создает составной план;
- apply выполняет только сохраненный `plan_id`;
- каждый шаг имеет readback;
- итоговый модуль привязан к группе меню;
- runtime smoke выполняет `get-data-simplified` по созданному представлению.

### `alterios_create_report_tab`

Статус: реализован на уровне API/readback; browser render evidence остается в
этапе 17.

Сценарий:

1. source view;
2. report template/source binding;
3. form tab с `params.openId=true`;
4. проверка `dataId: [openId]`;
5. static layout validation;
6. UI/render evidence при доступном renderer/export.

Критерии:

- report full/readback подтвержден;
- source view возвращает данные;
- form tab привязан к нужному report;
- current-record scope проверен через `dataId`;
- static layout validation выполняется по Stimulsoft template.

### `alterios_create_process_flow`

Статус: реализован на уровне typed API/readback и no-network tests. UI-проверка
открытия task-form остается частью этапа 17, если нужна browser evidence.

Сценарий:

1. task form;
2. scripts refs;
3. BPMN XML;
4. `camunda:formKey`;
5. process start;
6. active task readback;
7. optional task complete;
8. side-effect validation.

Критерии:

- BPMN refs валидны до write;
- start process создает ожидаемую task;
- task form открывается через formKey;
- side effects проверены readback-ом.

## Этап 17. UI/report validation

Статус: пропущен / отложен по решению пользователя от 2026-07-10. Replay/smoke
foundation реализован: `alterios-replay-smoke` и MCP tool `alterios_replay_smoke`
проверяют локальные контракты MCP без записи и могут дополнительно запускать
read-only live discovery.

Что остается в отложенной зоне:

1. Диагностика пустого Stimulsoft viewer.
2. Render/PDF/image validation для отчетов.
3. Проверка layout после render, а не только по JSON geometry.
4. Расширение form listener coverage:
   - add/update/remove listener;
   - validation script refs;
   - args map.
5. Расширение bulk actions:
   - selected manual script action;
   - selected process action;
   - destructive bulk delete только после отдельного dangerous workflow.
6. Replay/smoke command для проверки MCP после обновления. Готово.

## Этап 18. Inventory optimization

Статус: выполнен в write-preflight объеме с TTL и persisted diff cache.

Что сделано:

1. Кеш inventory в `artifacts/inventories/<profile>/<project_id>/` с TTL;
   стандартное значение — 300 секунд.
2. Автоматический live refresh просроченного snapshot и persisted diff в
   `latest-diff.json` плюс архив `diffs/`.
3. Health summary через `alterios-project-health` / `alterios_project_health`:
   - broken forms;
   - broken views/view fields;
   - missing script refs;
   - BPMN formKey errors;
   - report source/layout risks.
4. CLI/MCP read-only tool для быстрого health summary.

Осталось за пределами этого среза:

1. Render/PDF/image validation отчетов остается в отложенном stage 17.
2. Полностью инкрементальный backend diff без чтения проекта зависит от
   доступности reliable updatedAt/version по всем сущностям.

## Рабочий порядок

1. Закрыть этап 15 как базу для apply-by-plan. Готово.
2. Сделать `alterios_create_material_module`. Готово.
3. Сделать `alterios_create_report_tab`. Готово.
4. Сделать `alterios_create_process_flow`. Готово.
5. Stage 17 пропущен по решению пользователя; viewer/render diagnostics остается deferred.
6. Stage 18 закрыт как read-only write-preflight: cache/diff/project health.

## Этап 19. Fast live write и блокирующий UX-контракт

Статус: выполнен для сценариев создания и массовых side effects.

Что сделано:

1. `alterios_validate_form_contract` добавлен как строгий alias валидатора форм.
2. `alterios_fast_live_write` объединяет live preflight и сценарный вызов.
3. Режим остается двухфазным: `dry_run=true` сохраняет `plan_id`, а
   `dry_run=false` применяет тот же набор аргументов и проверенный план.
4. Разрешены только `alterios_create_material_module`,
   `alterios_create_report_tab` и `alterios_create_process_flow`.
5. Generic REST, security и destructive writes через fast-live недоступны.
6. Добавлены отдельные fast-live workflows для bulk manual script и BPMN
   process; оба используют cached health, точный список выбранных ID, plan/apply
   и построчный readback.
7. Destructive bulk delete вынесен в отдельный admin-only workflow с
   `ALTERIOS_MCP_ALLOW_DANGEROUS_WRITE=1`, `allow_destructive=true` и проверкой
   отсутствия каждой удаленной записи.
8. Process inventory для `alterios_runtime_info(include_processes=true)` теперь
   использует фильтрованный Windows scan и общий TTL cache с forced refresh.

Что еще не готово:

1. `server.py` остается физическим монолитом; профили разделяют реестр tools,
   но доменные пакеты пока не вынесены в отдельные registration modules.
2. Диагностика пустого Stimulsoft viewer и обязательный UI render-check для
   каждого нового паттерна остаются отдельным этапом.
3. Истинный backend incremental scan без полного project read требует надежных
   `updatedAt`/version-маркеров Alterios для всех проверяемых сущностей.
