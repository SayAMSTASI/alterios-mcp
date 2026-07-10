# Agents And Skills Plan

Этот документ задает контракт, как в `alterios-mcp` добавлять агентные роли и
skill-пакеты. Цель - не заменить MCP tools агентами, а сделать разработку,
инвентаризацию и проверку Alterios-поверхностей воспроизводимой.

## Agent Roles

| Agent | Назначение | Может менять код |
|---|---|---:|
| PM Agent | Ведет статус, этапы, риски, acceptance criteria, следующий шаг | Нет |
| Project Base Explorer | Делает read-only инвентаризацию project base, routes, response shapes | Нет |
| Write Tool Engineer | Реализует typed write tools в ограниченной зоне файлов | Да |
| Safety Verifier | Проверяет dry-run, write-gate, secret redaction, readback, UI/HAR evidence | Нет |
| Report/Dashboard Specialist | Проверяет Stimulsoft templates, Project Database datasource, report readback | Да, scoped |
| Skill Curator | Обновляет repo-owned skills после того, как tools и workflows проверены | Да, scoped |

Lead Engineer остается владельцем финальной интеграции, тестов, commit/push и
решения, что считается verified.

## Repo-Owned Skills

Skills добавляются только после того, как соответствующий workflow уже
проверен кодом или live sandbox. Иначе skill начнет закреплять догадки.

| Skill | Когда создавать | Что должен знать |
|---|---|---|
| `alterios-project-base-inventory` | После deep inventory project-base matrix | Профиль, project_id, listandcount, object totals, readback evidence |
| `alterios-form-view-surface` | После `docs/form-surface-inventory.md` и JSON-матрицы | view entity/field links, form tabs/actions, no-gap layout, F-pattern, role/source/style validation |
| `alterios-ui-icons-and-actions` | После `docs/icon-usage-matrix.json` и UTF-8 icon standard | Google Fonts Icons, size 16, color `#4B77D1`, action meaning, iconId validation |
| `alterios-script-bpmn-flow` | После `docs/script-bpmn-linkage.md` и parser refs | manual/event/diagram scripts, form actions, BPMN formKey/listeners/script refs, side effects |
| `alterios-write-tools` | После typed content/file/view/form/script/BPMN/report tools | write-gate, dry-run diff, managed marker, readback |
| `alterios-stimulsoft-project-db` | После report upsert/source validation tools | Stimulsoft JSON, Project Database datasource, report_full readback |
| `alterios-safety-verifier` | После scanner/test/readback workflow стабилизации | tests, secret redaction, dry-run/write-gate, UI/HAR evidence |
| `alterios-pm-control-loop` | После стабилизации project-status/project-management формата | stage control, acceptance criteria, risks, next steps |

Формат каждого skill folder:

```text
skills/<skill-name>/
  SKILL.md
  agents/openai.yaml
  references/
```

`SKILL.md` должен быть коротким: только триггеры, порядок работы и правила
безопасности. Подробные схемы и route examples уходят в `references/`.

## Control Loop

1. PM Agent открывает stage в `docs/project-status.md`.
2. Explorer Agent собирает read-only evidence и фиксирует маршруты/формы данных.
3. Write Tool Engineer добавляет typed tool и unit tests.
4. Safety Verifier запускает tests, secret scan, dry-run и live sandbox readback.
5. Skill Curator обновляет skill только после успешной проверки workflow.
6. Lead Engineer интегрирует, коммитит, пушит и обновляет статус.

## Что Не Делаем

- Не добавляем skill, который описывает непроверенный API как факт.
- Не даем агентам право на live write без Lead Engineer gate.
- Не смешиваем runtime service names и manual script UUID.
- Не считаем JSON-save достаточной проверкой для форм и отчетов, если результат
  должен быть виден оператору в UI.
