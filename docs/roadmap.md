# Дорожная карта Alterios MCP

Roadmap развивает production-oriented Alterios MCP 0.2, который безопасно
инвентаризирует, изменяет и проверяет реальные Alterios instances с множеством
проектов. Базовый контур уже включает 107 tools, профили registry, typed и
сценарные writes, `plan_id`, health cache, replay smoke, UX gates и readback.
Следующая работа направлена на совместимость разных установок, UI evidence и
release automation, а не на расширение монолитного `server.py`.

## 1. Foundation and safety - поддерживается

- Держать profile model на уровне instance: один profile равен одному Alterios
  instance, а не одному project.
- Расширять profile registry через `ALTERIOS_PROFILES` и
  `ALTERIOS_<PROFILE>_*` auto-discovery.
- Требовать, чтобы project-scoped tools принимали явный `project_id`.
- Использовать `ALTERIOS_<PROFILE>_PROJECT_ID` только как optional default для
  local convenience.
- Поддерживать `ALTERIOS_DOTENV_PATH` как основной способ подключить private
  dotenv без копирования secrets в репозиторий.
- Скрывать tokens, auth headers, passwords, cookies и API keys во всех tool
  responses и errors.
- Держать read-only defaults; writes - за `ALTERIOS_MCP_ALLOW_WRITE=1`,
  destructive/security writes - за `ALTERIOS_MCP_ALLOW_DANGEROUS_WRITE=1`.
- Поддерживать smoke checks для config loading, profile isolation, project
  override и secret redaction.

## 2. Read-only inventory - реализовано, расширяется по evidence

- Сначала inventory instance-level projects.
- Затем inventory project-level objects: content types, fields, views, forms,
  scripts, diagrams, contents, tasks, processes, reports, files, users/groups и
  view data.
- Нормализовать route metadata: scope, method, path, required params,
  pagination, filters, response shape и common errors.
- Добавлять stable MCP tools для common inventory tasks, а не полагаться только
  на generic REST calls.
- Сохранять reproducible JSON artifacts с profile/project context без secrets.

## 3. Каталог runtime-сервисов скриптов

- Расширять known script-service catalog: categories, arguments, permissions,
  read/write labels и examples.
- Probe read-only services по profile/project для body style, endpoint template
  behavior и response shape.
- Держать runtime service names отдельно от `/api/scripts/execute-manual`,
  который выполняет saved scripts by UUID.
- Классифицировать mutating services по risk и safeguards.
- Добавлять typed wrappers для high-value services только после проверки
  payload contracts.

## 4. Управляемая запись - реализовано для штатных сценариев

- Держать generic writes disabled by default и включать только через
  `ALTERIOS_MCP_ALLOW_WRITE=1`.
- Держать destructive/security generic writes за дополнительным
  `ALTERIOS_MCP_ALLOW_DANGEROUS_WRITE=1` и `allow_destructive=true`.
- Требовать явный `project_id`, verified profile output и narrow target
  arguments.
- Предпочитать typed write tools с validation, а не broad generic endpoints.
- Считать `alterios_rest_write` research/emergency layer, а не штатным
  operator interface.
- Запускать `alterios_write_safety_preflight` перед generic REST route, который
  еще не modeled typed tool.
- Расширять typed writes по entity family: content/files, views/forms,
  scripts, BPMN/process/tasks, reports, затем security/destructive flows.
- Добавлять dry-run validation, request summaries и redacted audit records.
- Подтверждать writes через API readback и, где нужно, UI-visible behavior.

## 5. Browser/UI discovery

- Снимать реальные UI network flows для list pages, forms, task screens,
  process actions, reports, dashboards, file fields и permission-sensitive
  flows.
- Маппить UI actions на REST endpoints и script-service calls.
- Использовать UI discovery для missing headers, route variants, encoded
  filters и project-context behavior.
- Проверять, что API changes совпадают с тем, что оператор видит в UI.

## 6. Release packaging - следующий этап

- Дать packaged console entry points и MCP server configuration examples.
- В MCP client configs использовать установленный `alterios-mcp` console
  script. `python -m alterios_mcp.server` оставлять только для диагностики и
  compatibility tests, не создавать для него вторую конфигурацию MCP.
- Документировать private configuration через environment variables и
  `ALTERIOS_DOTENV_PATH`; secrets не хранить и не копировать в repo.
- Добавить release smoke tests для config, readonly inventory, project override
  и write-gate behavior.
- Публиковать versioned artifacts, changelog notes, compatibility notes и
  example discovery outputs.
- Держать docs aligned с implemented tools, чтобы production operators видели,
  что shipped, experimental или planned.

## 7. Агенты и skills

- Держать agent roles как project control layer: PM, Business/System Analyst,
  Project Base Explorer, Data Model Engineer, View Builder, Form Surface
  Engineer, UI Icons & Actions Reviewer, Script/BPMN Flow Integrator,
  Report/Stimulsoft Specialist, Write Tool Engineer, Safety Verifier,
  Documentation Scribe и Skill Curator.
- Хранить operating contract в `docs/agents-and-skills.md`.
- Добавлять repo-owned skills только после реализации workflow и проверки
  через tests или live sandbox readback.
- Стартовый набор skills: project base inventory, requirements analyst, typed
  write tools, form/view surfaces, BPMN task flow и Stimulsoft Project
  Database reports.
- Не кодировать в skills непроверенное API behavior как факт.
