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

Что закрыть:

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

## Этап 18. Inventory optimization

Что сделать:

1. Кеш inventory в `artifacts/inventories/<profile>/<project_id>/`.
2. Diff-only scan по последнему snapshot.
3. Health summary:
   - broken forms;
   - broken views/view fields;
   - missing script refs;
   - BPMN formKey errors;
   - report source/layout/render risks.
4. CLI/MCP read-only tool для быстрого health summary.

## Рабочий порядок

1. Закрыть этап 15 как базу для apply-by-plan. Готово.
2. Сделать `alterios_create_material_module`. Готово.
3. Сделать `alterios_create_report_tab`. Готово.
4. Сделать `alterios_create_process_flow`. Готово.
5. После сценарных tools перейти к render validation. Следующий шаг.
6. После render validation перейти к inventory cache/diff health.
