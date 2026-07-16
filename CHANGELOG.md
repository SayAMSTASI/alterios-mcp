# История изменений

## 0.2.1 - 2026-07-17

### Исправлено

- Синхронизированы код, JSON и Markdown UX-контракта.
- Валидатор учитывает `displaying.header`, обязательный верхний отступ заголовка
  таблицы, пустые участки формы, ширину data-ячеек, иконки и меню действий.
- Сценарий модуля материалов формирует согласованные пользовательские заголовки,
  не добавляет заголовок нетабличной ячейке комментариев и перед apply требует
  проектные UUID иконок.

### Совместимость

- Публичные имена и схемы MCP tools не изменены.

## 0.2.0 - 2026-07-17

### Добавлено

- Профили MCP tools `live`, `discovery`, `admin` и `full`.
- Fast live preflight, cached project health, write plans и write journal.
- Сценарные workflows для модулей материалов, отчётных вкладок и процессов.
- Fast-live workflows для bulk manual script, process и destructive delete.
- Блокирующий UX-контракт форм и printable render/PDF validation.
- Private Gitea workboard, agent evidence и stage transitions.

### Изменено

- `server.py` превращён в composition root.
- Регистрация MCP tools разделена на 12 доменных модулей в `tools/`.
- Бизнес-операции перенесены в `scenarios/`, payload builders - в `builders/`,
  проверки контрактов - в `validators/`.
- README переписан как актуальная инструкция установки, запуска и эксплуатации.

### Совместимость

- Сохранены 107 публичных имён MCP tools и их схемы аргументов.
- Python-level imports из `alterios_mcp.server` временно поддерживаются
  compatibility bridge.
- После обновления требуется переустановка editable package и перезапуск
  MCP-клиента, чтобы завершить старый процесс с предыдущим registry.

## 0.1.0

- Первоначальная поставка discovery, typed writes, project inventory и
  документации Alterios MCP.
