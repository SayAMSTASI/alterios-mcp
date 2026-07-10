# Дорожная карта Alterios MCP

Roadmap ведет к production-oriented Alterios MCP, который безопасно
инвентаризирует, изменяет и проверяет реальные Alterios instances с множеством
проектов. Текущий код уже содержит read-only discovery и guarded generic
writes; оставшаяся работа - довести coverage, safety и release-процесс до
повторяемого состояния.

## 1. Foundation and safety

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

## 2. Complete read-only inventory

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

## 4. Управляемая запись

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

## 6. Release packaging

- Дать packaged console entry points и MCP server configuration examples.
- В MCP client configs предпочитать установленный `alterios-mcp` console
  script; `python -m alterios_mcp.server` держать как fallback.
- Документировать private configuration через environment variables и
  `ALTERIOS_DOTENV_PATH`; secrets не хранить и не копировать в repo.
- Добавить release smoke tests для config, readonly inventory, project override
  и write-gate behavior.
- Публиковать versioned artifacts, changelog notes, compatibility notes и
  example discovery outputs.
- Держать docs aligned с implemented tools, чтобы production operators видели,
  что shipped, experimental или planned.

## 7. Агенты и skills

- Держать agent roles как project control layer: PM, Project Base Explorer,
  Data Model Engineer, View Builder, Form Surface Engineer, UI Icons & Actions
  Reviewer, Script/BPMN Flow Integrator, Report/Stimulsoft Specialist, Write
  Tool Engineer, Safety Verifier и Skill Curator.
- Хранить operating contract в `docs/agents-and-skills.md`.
- Добавлять repo-owned skills только после реализации workflow и проверки
  через tests или live sandbox readback.
- Стартовый набор skills: project base inventory, typed write tools,
  form/view surfaces, BPMN task flow и Stimulsoft Project Database reports.
- Не кодировать в skills непроверенное API behavior как факт.
