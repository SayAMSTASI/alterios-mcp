# UI evidence по форматам представлений

Дата: 2026-07-11.

Контур: тестовый sandbox-проект Alterios. Реальные URL, project id, пользователи,
email и токены в документ не включены.

## Проверка

Для каждого sandbox-представления открыта страница редактирования в UI,
проверены видимые настройки, включенный experimental mode, выполнено действие
`Сохранить и запустить предпросмотр`, затем проверен preview.

| Формат | Настройки в UI | Preview evidence | Итог |
|---|---|---|---|
| `table` | Формат "Таблица", `Шаблон заголовка`, experimental mode, `mergeRows` | Таблица с 2 строками, 3 table row nodes, текст `Format probe 1/2` | Подтвержден |
| `reference` | Формат "Ссылка на материал", `Шаблон заголовка`, experimental mode | Save/preview без ошибки, но standalone preview строки не выводит | Подтвержден как selector/ref source, не как самостоятельный список |
| `grid` | Формат "Сетка", `desc`, `iconField`, `iconWidth`, `iconHeight`, experimental mode | Плиточный вывод, 6 grid-like nodes, текст `Format probe 1/2` | Подтвержден |
| `list` | Формат "Список", `Шаблон заголовка`, experimental mode | Раскрываемый список, 3 list/expansion nodes, текст `Format probe 1/2` | Подтвержден |
| `gantt` | Формат "Диаграмма Гантта", `date1`, `date2`, planned dates, `title`, `resource`, `defaultView=month`, show flags | Gantt table/timeline, 83 gantt-like nodes, текст `Format probe 1/2` | Подтвержден |
| `leaflet` | Формат "Карта", min/max zoom, layers, default marker source, geo fields, marker source | Карта, 2 leaflet containers, 2 marker icons, 2 marker shadows, 2 interactive layers | Подтвержден |
| `calendar` | Формат "Календарь", `title`, `startDate`, `endDate`, `bgColor`, experimental mode | Месячная сетка, 2 calendar nodes, события `Format probe 1/2` | Подтвержден |

## Найденные правила

- `calendar`: UI-save требует `settings.title`; без него форма показывает
  `Ошибка / Проверьте поля формы`. При заполненном `title` сохраняются
  `startDate`, `endDate`, `bgColor`, `engineVersion`, preview показывает события.
- `leaflet`: для отображения маркеров `geo` field value должен быть массивом
  GeoJSON `Feature`; bare geometry `Point` сохраняется, но не дает marker icons.
- `reference`: standalone preview не является пользовательским списком. Этот
  формат нужно проверять как источник выбора для `ref source=view`.
- Для всех проверенных форматов страница редактирования показывает
  `Экспериментальный режим`, и preview после save не возвращает ошибок.

## Локальные артефакты

Скриншоты и sanitized JSON evidence сохранены локально:

`artifacts/ui-evidence/view-formats-2026-07-11/`

Каталог `artifacts/` не коммитится.
