# Дорожная карта Alterios MCP

Актуализировано: 17 июля 2026 года.

Roadmap отделяет подтвержденное состояние продукта от прогноза. Дата этапа
является целевым сроком, а не обещанием: этап закрывается только после выполнения
stage gate. Если внешний Alterios-контур, browser evidence или release-доступ
недоступны, срок пересматривается, а этап получает статус `Blocked` или `Risk`.

## 1. Текущий состав

| Область | Подтвержденное состояние |
|---|---|
| Версия | `0.2.2` |
| Публичный MCP registry | 108 tools |
| Профили tools | `live` - 81, `discovery` - 55, `admin` - 106, `full` - 108 |
| Архитектура | `server.py` - composition root на 102 строки; регистрация разделена на 12 доменов |
| Рабочие слои | `tools/`, `scenarios/`, `builders/`, `validators/` |
| Запись | typed writes, сценарии, `plan_id`, write journal, readback и dangerous gates |
| Сценарии | модуль материалов, отчетная вкладка, BPMN/process flow, bulk script/process/delete |
| Диагностика | project health с TTL/diff cache, runtime info, doctor, release/replay smoke и report viewer diagnostics |
| UX-контроль | блокирующий form contract, icon/action contract, printable/PDF validation |
| Управление работой | private Gitea/local fallback, agent evidence и stage transitions |
| Автотесты | 320 тестов; replay smoke - 6 успешных проверок из 6, 1 live-check пропускается без явного флага |
| Производительность импорта | 1,36-1,78 секунды на текущем Windows runtime при пяти отдельных запусках |

Публичные имена tools, JSON Schema аргументов и состав профилей зафиксированы в
`tests/fixtures/tool_registry_snapshot.json`. Изменение этого снимка считается
изменением публичного контракта и требует отдельного решения о совместимости.

## 2. Статус предыдущего плана

| Этап | Статус | Результат |
|---|---|---|
| 1-14. Discovery и typed API foundation | Done | Инвентаризация, проектные сущности, формы, scripts/BPMN, reports, files и security surface |
| 15. Write workflow foundation | Done | `plan_id`, journal, apply только проверенного плана |
| 16. Сценарные tools | Done | Material module, report tab и process flow |
| 17. UI/report validation | Done with Risk | Printable/PDF и form listeners закрыты; embedded Stimulsoft viewer требует отдельного UI evidence |
| 18. Inventory optimization | Done | TTL cache, persisted diff и project health |
| 19. Fast live write и UX contract | Done | Fast-live workflows, blocking validators, runtime optimization и разделение монолита |

Исторические критерии этапов 15-19 сохранены в
`docs/optimization-plan.md`. Новая разработка начинается с этапа 20.

## 3. Этап 20. Стабилизация 0.2.2

**Фактическая дата:** 17 июля 2026 года.

**Статус:** Done.

**Ответственный:** Lead Engineer.

Результат:

1. Добавлена `alterios-doctor`-проверка: console entry point, Python, dotenv,
   tool profile, write gates и доступность профилей из чистой пользовательской
   PowerShell-сессии.
2. Добавлен GitHub Actions matrix для Python 3.11-3.13: pytest, registry snapshot,
   replay smoke, sensitive-data scan и сборка wheel.
3. Зафиксирован startup benchmark с бюджетом 2 секунды на
   эталонном Windows runtime без OS process scan.
4. Добавлен `alterios_diagnose_report_viewer`: source
   data, template, container state и browser evidence должны проверяться
   раздельно.
5. Синхронизированы README, administrator guide, changelog и фактические
   entry points.

Stage gate:

- установка в чистое virtual environment завершается одной документированной
  командой;
- `doctor`, полный pytest и replay smoke проходят;
- CI собирает wheel и не публикует secrets;
- viewer limitation воспроизводимо диагностируется и явно отражается в
  результате, даже если браузерный рендер внешнего контура недоступен.

## 4. Этап 21. Совместимость Alterios instances

**Срок:** 27 июля - 7 августа 2026 года.

**Статус:** Next.

**Ответственный:** Project Base Explorer.

Задачи:

1. Составить обезличенную compatibility matrix минимум для двух разных
   Alterios instances.
2. Добавить capability discovery для route variants, script services,
   view formats, report export и security endpoints.
3. Разделить `supported`, `unsupported`, `requires UI evidence` и
   `requires dangerous gate` в machine-readable capability result.
4. Обеспечить graceful degradation: отсутствие необязательного endpoint не
   должно ломать весь inventory или startup MCP.
5. Добавить compatibility fixtures и no-network regression tests.

Stage gate:

- одинаковый пакет запускается минимум на двух instances без изменения кода;
- различия маршрутов отражаются в capability report;
- базовые inventory, material module dry-run, report dry-run и process dry-run
  проходят на обоих профилях;
- публичные business URL, UUID, названия материалов и данные не попадают в Git.

## 5. Пользовательские расширения

**Статус:** Deferred outside core.

Плагинная система исключена из обязательного Roadmap. Пользователь может
создавать собственные Python-пакеты, skills или обертки над MCP под свои
бизнес-сценарии. Core сохраняет стабильные registration/scenario/validator
границы, но не берет на себя discovery и сопровождение сторонних плагинов.

## 6. Этап 23. Release packaging и обновление

**Фактическая дата:** 17 июля 2026 года.

**Статус:** Done.

**Ответственный:** Lead Engineer.

Результат:

1. Добавлена публикация versioned wheel и GitHub Release с checksum, changelog и
   compatibility notes.
2. Добавлен `manage_release.ps1` для install, update и rollback
   для Windows.
3. Оставить в MCP client config один console entry point `alterios-mcp`;
   диагностические способы запуска не должны создавать дубли процессов.
4. Добавлен `alterios-release-smoke` для doctor, registry profiles и replay.
5. Обновлена инструкция администратора по установке и обновлению без clone.

Stage gate:

- новый пользователь устанавливает MCP по README без локального clone;
- update и rollback проверены в отдельном virtual environment;
- release artifact проходит CI, replay smoke и sensitive-data scan;
- после restart существует один логический MCP instance без stale runtime.

## 7. Этап 24. Пилот и решение о 1.0

**Срок:** 10-21 августа 2026 года.

**Статус:** Planned.

**Ответственный:** Safety Verifier.

Задачи:

1. Выполнить пилот минимум на двух Alterios instances.
2. Проверить end-to-end сценарии: material module, printable report,
   BPMN/process, selected bulk operation и guarded destructive dry-run.
3. Зафиксировать API readback, UI spot-check и rollback notes по каждому
   пользовательскому паттерну.
4. Проверить отсутствие secrets и проектных данных в публичных artifacts.
5. Сформировать go/no-go решение для `1.0` и список известных ограничений.

Stage gate:

- нет открытых Critical/High дефектов безопасности или потери данных;
- все обязательные сценарии имеют воспроизводимый evidence;
- документация соответствует release package;
- оставшиеся ограничения явно классифицированы как Risk или Deferred.

Целевая дата решения о выпуске `1.0`: **21 августа 2026 года**. Если stage gate
не пройден, версия остается `0.x`, а новая дата назначается после разбора
конкретных блокеров.

## 8. Постоянно поддерживаемые контуры

Эти направления не являются отдельными разовыми этапами и проверяются в каждом
release slice:

- profile isolation и явный `project_id`;
- secret redaction и public-tree sensitive scan;
- read-only defaults, write gates и destructive gates;
- dry-run -> reviewed `plan_id` -> apply -> API readback -> UI spot-check;
- сохранение совместимости registry или явное versioned breaking change;
- актуальность skills только после подтверждения поведением кода и live
  evidence;
- один accountable owner на этап и независимый Verifier перед `Done`.

## 9. Правила пересмотра сроков

Roadmap пересматривается после каждого завершенного этапа или при появлении
внешнего блокера. Обновление должно содержать:

1. фактическую дату и commit/release evidence;
2. незакрытый критерий stage gate;
3. причину изменения срока;
4. нового ответственного и ближайший проверяемый результат;
5. влияние на целевую дату следующего release.

Новые tools сами по себе не являются прогрессом Roadmap. Прогресс учитывается,
только если workflow реализован, протестирован, задокументирован и доступен в
установленном MCP runtime.
