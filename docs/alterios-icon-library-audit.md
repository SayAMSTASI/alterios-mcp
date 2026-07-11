# Аудит библиотеки иконок Alterios

Дата: 2026-07-11

## Проверка

Проверялась git-библиотека `assets/icons/project-public`, которая используется MCP для загрузки проектных иконок через `alterios_ensure_project_icon_library`.

Стандарт:

- иконка скачивается из Google Fonts Icons с UI Size `16`;
- фактические SVG `width`/`height` сохраняются такими, как их отдает Google Fonts;
- размер SVG вручную не переписывается;
- `fill="#4B77D1"`;
- иконки должны оставаться Google Fonts Icons;
- `iconId` в Alterios должен ссылаться только на UUID файла, загруженного в целевой проект.

## Найдено до исправления

- 13 из 39 SVG имели цвет не `#4B77D1`:
  - `add_2`;
  - `attach_file_add`;
  - `calendar_check`;
  - `delete`;
  - `directory_sync`;
  - `edit`;
  - `history`;
  - `info`;
  - `keyboard_return`;
  - `list_alt_add`;
  - `menu`;
  - `preview`;
  - `save`.

## Исправлено

- Фактические `width`/`height` SVG оставлены в скачанном из Google Fonts виде.
- Все 39 SVG нормализованы до `fill="#4B77D1"`.
- `manifest.json` пересчитан: `bytes`, `sha256`, правила `svg_size` и `svg_color`.
- В `docs/alterios-icons-and-actions-catalog.md` добавлены визуальные превью всех 39 иконок.
- Добавлен тест `tests/test_icon_library.py`, который проверяет manifest, наличие SVG dimensions, цвет `#4B77D1` и preview-ссылки в каталоге.

## Важное правило применения

При работе с новым проектом MCP не переносит UUID иконок между проектами. Перед записью формы, группы или действия он должен:

1. проверить текущий состав иконок проекта;
2. загрузить недостающие SVG из `assets/icons/project-public`;
3. использовать только UUID, возвращенный для целевого проекта.
