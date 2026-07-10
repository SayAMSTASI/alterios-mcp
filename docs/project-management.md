# Управление проектом и мультиагентный контур

Проект использует легкий PM control loop, чтобы работа нескольких агентов была
видимой, проверяемой и привязанной к подтвержденным результатам.

## Роли

| Роль | Ответственность | Пишет код |
|---|---|---:|
| Lead Engineer | Финальная интеграция, проверки, commit и push. | Да |
| PM Agent | Статус задач, границы этапов, риски, решения и следующие действия. | Нет |
| Explorer Agent | Ограниченные вопросы по codebase/API с evidence и ссылками на файлы. | Нет |
| Worker Agent | Реализация ограниченной задачи в заранее заданной зоне файлов. | Да |
| Verifier Agent | Независимые проверки, обзор рисков и отчет о gaps. | Нет |
| Business/System Analyst / Аналитик требований | Постановка, ТРЗ, сценарии, требования к views/forms/scripts/BPMN/reports и acceptance criteria. | Нет |
| Documentation Scribe / Писарь | Инструкции администратора/пользователя и ГОСТ/ЕСПД-документация по проверенным источникам. | Нет |

Lead Engineer отвечает за итоговое состояние репозитория. Subagents могут
предлагать правки или патчи, но их работа включается только после review и
проверок.

## Контрольные артефакты

- `docs/project-status.md` - текущая status board.
- `docs/roadmap.md` - durable delivery roadmap.
- `docs/discovery-plan.md` - стратегия endpoint discovery и inventory.
- `docs/gost-documentation-scribe-agent.md` - локальный playbook для
  инструкций администратора/пользователя и ГОСТ-oriented документации.
- Commit messages фиксируют завершенные slices.
- Verification evidence суммируется в status updates и final answers.

## Stage gate

Каждый этап должен иметь:

- scope и ожидаемый outcome;
- owner role;
- acceptance criteria;
- verification commands или live smoke checks;
- risks или blocked items;
- commit hash после завершения.

Задача не считается `Done`, пока code/docs не закоммичены и нужные проверки не
прошли, либо статус явно не говорит, что именно не удалось проверить.

## Статусы

| Статус | Значение |
|---|---|
| Done | Реализовано, проверено, закоммичено и отправлено в remote. |
| In Progress | Сейчас реализуется или проверяется. |
| Next | Готово к старту после активной задачи. |
| Blocked | Нужен пользовательский input или внешнее изменение состояния. |
| Deferred | Валидная работа, осознанно отложена. |
| Risk | Известная неопределенность, которую надо закрыть до release. |

## Правила мультиагентной работы

- Запускать agents только для bounded work, которую можно выполнять
  параллельно.
- Давать каждому Worker Agent явную file/module ownership scope.
- Предупреждать Worker Agent, что в дереве могут быть чужие изменения и их
  нельзя откатывать.
- PM Agent остается read-only, если его явно не попросили менять проектные
  документы.
- Завершенных agents закрывать, чтобы не оставались stale work items.
- Не использовать subagent output как proof, пока Lead Engineer сам его не
  проверит.

## Ритм отчетности

В конце каждого implementation stage обновлять `docs/project-status.md`:

- что сделано;
- commit hash;
- какие проверки запущены и с каким результатом;
- live-smoke result, если применимо;
- новые risks;
- следующий этап и первые конкретные задачи.

Для длинных этапов status board обновляется после каждого meaningful
mergeable slice.
