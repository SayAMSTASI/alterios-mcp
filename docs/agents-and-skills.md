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
| `alterios-project-base` | После typed inventory/readback helpers | Профиль, project_id, listandcount, view data, Project Database evidence |
| `alterios-write-tools` | После первых typed content/file tools | write-gate, dry-run diff, managed marker, readback |
| `alterios-form-view-surface` | После typed view/form tools | view entity/field links, form tabs/actions, UI validation |
| `alterios-bpmn-task-flow` | После BPMN/process/task tools | diagram XML, process start, task complete, side-effect validation |
| `alterios-stimulsoft-project-db` | После report upsert tool | Stimulsoft JSON, Project Database datasource, report_full readback |

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
