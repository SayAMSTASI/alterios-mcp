# Gitea как закрытое рабочее поле

Этот документ описывает, как использовать приватный Gitea как Jira-подобное
рабочее поле для реальных Alterios-задач, не публикуя проектную информацию в
публичный репозиторий `alterios-mcp`.

## 1. Назначение

Gitea-workboard нужен для хранения реальных рабочих задач:

- постановки по проектам;
- sprint backlog;
- Kanban-статусы;
- ответственные по этапам;
- отчеты агентов;
- ссылки на закрытые Alterios-проекты;
- evidence, screenshots, HAR, readback и рабочие заметки.

Публичный GitHub-репозиторий `alterios-mcp` хранит только MCP, правила,
шаблоны, обезличенные примеры и reusable skills. Реальные задачи и данные
клиентов должны храниться в закрытом Gitea или локальном private workboard.

## 2. Граница данных

| Где хранится | Можно хранить | Нельзя хранить |
|---|---|---|
| `alterios-mcp` GitHub | MCP code, tests, docs, templates, skills, обезличенные правила | Реальные URL, project ids, users, roles, client data, raw HAR, screenshots |
| Private Gitea | Реальные задачи, постановки, sprint board, evidence, agent reports | Токены, пароли, секреты в открытом тексте |
| Локальные artifacts | Временные выгрузки, write-plans, write-journal, raw inventory | Долгосрочные артефакты без владельца и срока хранения |

Если реальная задача выявила полезное общее правило, в `alterios-mcp` переносится
только обезличенное улучшение: skill, validator, template, doc или typed tool.

## 3. Модель Gitea

| Gitea объект | Как используем |
|---|---|
| Organization/User | Закрытый контур команды |
| Repository | Отдельный private repo, например `alterios-workboard` |
| Issues | Рабочие задачи, постановки, bugs, исследования, проверки |
| Projects | Kanban-доска |
| Milestones | Спринты или этапы поставки |
| Labels | Тип задачи, область, stage, риск, статус проверки |
| Assignees | Ответственные лица |
| Comments | Отчеты агентов, решения, результаты проверок |
| Attachments | Evidence, screenshots, export-файлы, если разрешено политикой контура |
| Pull requests | Только если в private repo есть код/конфиги, которые реально меняются |

## 4. Рекомендуемые статусы Kanban

Базовые колонки проекта:

1. `Backlog` - идея или входящий запрос.
2. `Ready` - есть постановка, Mermaid-схема и acceptance criteria.
3. `In Progress` - идет discovery/design/build.
4. `Review` - результат собран, требуется инженерная проверка.
5. `Verify` - выполняются readback, UI evidence, tests, safety checks.
6. `Done` - задача закрыта по Definition of Done.
7. `Blocked` - есть внешний блокер или риск, который не может быть снят агентом.

Статус `Done` нельзя ставить без ответственного, артефактов и проверки.

## 5. Спринты

Milestone в Gitea используется как sprint.

Рекомендуемый формат имени:

```text
2026-07-S1 Alterios delivery
```

Минимальные поля sprint:

- цель sprint;
- период;
- владелец;
- список issues;
- Definition of Done;
- риски и блокеры;
- ссылка на итоговый отчет.

## 6. Типы задач

| Тип | Когда использовать |
|---|---|
| `brief` | Постановка, ТРЗ, формализация бизнес-запроса |
| `feature` | Новая функция, интерфейс, модуль, сценарий |
| `bug` | Ошибка MCP, формы, представления, скрипта, отчета |
| `research` | Read-only исследование API/UI/проектной базы |
| `verification` | Независимая проверка, smoke, UI evidence, safety review |
| `docs` | Инструкция, регламент, описание workflow |
| `chore` | Техническая задача без пользовательского эффекта |

## 7. Обязательная структура Issue

Issue по рабочей задаче должен содержать:

- тип задачи;
- ответственного владельца результата;
- sprint/milestone;
- stage gate;
- Mermaid-схему;
- постановку;
- acceptance criteria;
- затрагиваемые Alterios-объекты;
- план проверки;
- Git-решение: что пойдет в public MCP repo, а что останется private;
- ссылки на evidence или artifacts.

Для шаблонов используйте:

- `templates/gitea/issue-brief.md`;
- `templates/gitea/issue-task.md`;
- `templates/gitea/agent-report.md`.

## 8. Ответственные лица

У каждого stage должен быть один ответственный владелец результата.

| Stage | Типовой ответственный |
|---|---|
| Intake | PM Control Loop / Lead Engineer |
| Постановка | Business/System Analyst |
| Discovery | Project Base Explorer |
| Design | Data Model Engineer / View Builder / Form Surface Engineer |
| Build | профильный инженер |
| Verify | Safety Verifier |
| Docs/Git | Lead Engineer / Documentation Scribe |

Соисполнители могут быть указаны в задаче, но владелец stage должен быть один.

## 9. Комментарии агентов

Каждый агент пишет отчет в комментарий issue по шаблону:

```text
Роль:
Scope:
Что сделано:
Артефакты:
Проверка:
Риски:
Следующий шаг:
```

Агент не переводит задачу в `Done` сам, если не является ответственным за
закрывающий stage.

## 10. Связь с Git

В issue можно указывать commit hash из публичного `alterios-mcp`, если задача
породила reusable-изменение.

Правило:

- реальная задача остается в Gitea;
- reusable MCP-изменение пушится в GitHub;
- в GitHub commit message не добавляются названия реальных проектов,
  пользователей, URL и project ids.

## 11. Подключение через окружение

Секреты хранятся только во внешнем private `.env`.

Пример переменных:

```env
GITEA_BASE_URL=https://gitea.example.local
GITEA_TOKEN=put-token-here
GITEA_OWNER=alterios-team
GITEA_REPO=alterios-workboard
GITEA_DEFAULT_PROJECT=Alterios Delivery
GITEA_DEFAULT_MILESTONE=2026-07-S1
```

В публичном `.env.example` допускаются только placeholders.

## 12. Будущие MCP tools

Когда Gitea workflow стабилизируется, можно добавить typed tools:

- `gitea_create_work_item`;
- `gitea_update_work_item_status`;
- `gitea_add_agent_report`;
- `gitea_create_sprint`;
- `gitea_list_sprint_tasks`;
- `gitea_link_commit`;
- `gitea_close_work_item`.

Каждый write-tool должен иметь dry-run, redaction, explicit repo target и
проверку, что он пишет в private Gitea, а не в публичный `alterios-mcp`.

## 13. Definition of Done для Gitea-задачи

Задача может быть закрыта только если:

- есть постановка с Mermaid-схемой;
- назначен ответственный по каждому активному stage;
- acceptance criteria закрыты;
- проверка выполнена и описана;
- reusable-изменения, если были, запушены в `alterios-mcp`;
- private evidence осталось в Gitea или локальном закрытом контуре;
- финальный отчет содержит состав объектов: таблицы/типы материалов, поля,
  представления, формы, скрипты, BPMN, отчеты и ограничения, если они применимы.
