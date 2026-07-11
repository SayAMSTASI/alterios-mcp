# Исследование типов материалов, полей и представлений

Дата: 2026-07-11.

Контур: тестовый sandbox-проект Alterios. В документ намеренно не включены реальные
адреса системы, рабочие названия проектов, пользователи, email и токены.

## Цель

Проверить, как MCP должен создавать и настраивать:

- типы материалов и поля с пользовательскими описаниями и подсказками;
- представления разных форматов и режимов;
- связи через `ref`-поля и joined view;
- UI-формы, где пользователь видит результаты проверки представлений.

## Подтвержденный enum форматов представлений

Клиентский SPA-код Alterios содержит следующие значения `view.format`:

| Формат | Назначение |
|---|---|
| `table` | Таблица, основной формат для списков и joined views. |
| `grid` | Плиточный вывод с описанием и опциональной иконкой. |
| `list` | Список в виде раскрываемых строк без отдельной формы настроек. |
| `leaflet` | Карта по `geo`-полям. |
| `gantt` | Диаграмма Ганта по датам и ресурсам. |
| `reference` | Представление-источник для выбора значения в `ref`-полях. |
| `calendar` | Календарный вывод по полям дат. |

В frontend `calendar` и `leaflet` отмечены как non-paginable formats. Для них
нельзя полагаться только на обычную постраничную таблицу.

Формат `cards` не подтвержден как актуальный `view.format`: в frontend enum его
нет. Если где-то встречается слово `cards`, его нельзя считать рабочим форматом
представления без отдельного UI/HAR/API evidence.

## Что создано в sandbox

| Объект | Проверенный результат |
|---|---|
| Справочный тип материала для статусов | Поля code/name/active, две тестовые записи, reference view для выбора значения. |
| Основной тип материала для проверки представлений | Поля text, number, date, boolean, list single, list multiple, ref by view, ref by basic, file. |
| Короткий тип материала для relation join | Короткий `fieldNamePrefix`, короткие mname, две записи со ссылкой на статус. |
| Тип материала для проверки view formats | Поля title, description, start date, end date, resource, color, geo point, две строки данных. |
| `table` experimental/v2 | View saved, `get-data` и `get-data-simplified` вернули строки. |
| `reference` experimental/v2 | View saved, пригоден как источник для `ref source=view`. |
| `grid` experimental/v2 | View saved, `desc`, `iconWidth`, `iconHeight` сохранены, данные читаются. |
| `list` experimental/v2 | View saved без дополнительных настроек, данные читаются. |
| `gantt` experimental/v2 | View saved, настройки дат/ресурса/readback сохранены, данные читаются. |
| `leaflet` experimental/v2 | View saved, `geoFields` с `markerIcons=default` сохранены, данные читаются. |
| `calendar` experimental/v2 | Формат и вывод подтверждены, но backend-save отбрасывает `startDate/endDate`; требуется UI/HAR или отдельный route. |
| Классическое `table` без `engineVersion` | Данные читаются, но режим считается исключением и требует явного `allow_legacy_mode`. |
| UI-форма с вкладками проверки | Форма содержит вкладки v2 table, reference, relation join и classic table; analyzer вернул 0 issues. |

## Матрица форматов представлений

| Формат | Режим | Статус | Настройки | Правило для MCP |
|---|---|---|---|---|
| `table` | experimental/v2 | live-проверен | `engineVersion` | Использовать по умолчанию для списков, таблиц, joined views и встроенных списков. |
| `reference` | experimental/v2 | live-проверен | `engineVersion` | Использовать как источник выбора для `ref`-полей и справочников. |
| `grid` | experimental/v2 | live-проверен | `desc`, `iconField`, `iconWidth`, `iconHeight`, `engineVersion` | Использовать для плиточного каталога, когда нужен короткий визуальный обзор записей. |
| `list` | experimental/v2 | live-проверен | `engineVersion` | Использовать для компактного списка с раскрытием строки; отдельной формы настроек во frontend не найдено. |
| `gantt` | experimental/v2 | live-проверен | `defaultView`, `date1`, `date2`, `plannedDate1`, `plannedDate2`, `title`, `resource`, `completion`, `showDate`, `showDuration`, `showPlannedDate`, `showResource`, `showCompletion`, `engineVersion` | Перед сохранением требовать `defaultView`, `date1.field`, `date2.field`; после сохранения проверять `get-data`. |
| `leaflet` | experimental/v2 | live-проверен | `geoFields`, `markerIcons`, `tileLayers`, `featureLayers`, `defaultMarkerSource`, `minZoom`, `maxZoom`, `engineVersion` | Сначала создать view и поля, затем сохранить `geoFields` по view-field `mname` без `field_`; `markerIcons` обязателен. |
| `calendar` | experimental/v2 | частично подтвержден | frontend читает `startDate`, `endDate`, `bgColor`, `engineVersion`; readback сохраняет только `bgColor` и `engineVersion` | Не считать календарь готовым после save. Нужен UI/HAR evidence или отдельный route, который сохраняет `startDate/endDate`. |
| `table` | classic/legacy | live-проверен как исключение | settings пустой или без `engineVersion` | Создавать только при явном `allow_legacy_mode=true` и документированном evidence. |

## Правила режимов

1. Базовый режим для новых представлений - experimental/v2:

```json
{
  "settings": {
    "engineVersion": "v2"
  }
}
```

2. Если settings пустой или без `engineVersion`, MCP считает это legacy/classic.
3. Legacy/classic нельзя создавать случайно. Для typed write нужен явный флаг
   `allow_legacy_mode=true`.
4. Если часть UI действительно работает только в classic/standard режиме, сначала
   нужно получить read-only/UI/HAR evidence, затем записывать как documented exception.
5. После изменения view одного успешного save недостаточно: обязательны populated
   view fields и `get-data` или `get-data-simplified`.

## Настройки форматов

### Table

- Минимум: `settings.engineVersion = "v2"`.
- Для joined views сначала читать реальные `viewField.mname`.
- Технические `_id`, helper relation fields и пустые сервисные поля скрывать в
  пользовательском списке.

### Reference

- Минимум: `settings.engineVersion = "v2"`.
- Используется в `ref source=view`.
- Для справочника выводить человекочитаемые поля, а не технический id.

### Grid

- `desc` указывает view-field mname для описания карточки.
- `iconField` можно использовать, если иконка хранится в поле.
- `iconWidth` и `iconHeight` задают размер иконки.
- Данные проверяются через `get-data`; `get-data-simplified` возвращает строки без
  headers/settings.

### List

- Отдельная config-форма во frontend не найдена.
- Минимум: `settings.engineVersion = "v2"`.
- Подходит для компактного вывода, где строка раскрывает набор полей.

### Gantt

Обязательные настройки:

```json
{
  "defaultView": "month",
  "date1": { "field": "<start-date-view-field-mname>", "offset": 0 },
  "date2": { "field": "<end-date-view-field-mname>", "offset": 0 }
}
```

Дополнительные настройки:

- `plannedDate1`, `plannedDate2` - плановые даты;
- `title` - поле заголовка задачи;
- `resource` - поле ресурса;
- `completion` - поле процента/статуса выполнения;
- `showDate`, `showDuration`, `showPlannedDate`, `showResource`, `showCompletion`.

Допустимые `defaultView`: `day`, `week`, `month`, `quarter`, `year`.

### Leaflet

Рабочий порядок:

1. Создать view с `format = "leaflet"` и `engineVersion = "v2"`.
2. Привязать entity и view fields, включая persisted field типа `geo`.
3. Прочитать populated view fields.
4. Сохранить `settings.geoFields[]` по view-field `mname`.
5. Проверить `get-data`.

Минимальный рабочий фрагмент:

```json
{
  "geoFields": [
    {
      "name": "<geo-view-field-mname>",
      "layer": null,
      "visibleByDefault": true,
      "markerIcons": "default"
    }
  ],
  "defaultMarkerSource": "default",
  "tileLayers": [],
  "featureLayers": [],
  "minZoom": 1,
  "maxZoom": 17,
  "engineVersion": "v2"
}
```

`markerIcons` обязателен. Допустимые значения: `default`, `img`, `field`.

### Calendar

Frontend config/output использует:

- `settings.startDate` - обязательное поле даты начала;
- `settings.endDate` - поле даты окончания;
- `settings.bgColor` - поле цвета события.

Live probing показал, что текущий `/api/views` save/readback сохраняет только
`bgColor` и `engineVersion`, а `startDate/endDate` отбрасывает. Поэтому MCP не
должен объявлять календарь готовым без дополнительного UI/HAR evidence. Нужен
отдельный проход по пользовательскому интерфейсу или поиск специального route,
который сохраняет настройки дат.

## Поля типов материалов

| Тип поля | Live-проверка | Настройки и вывод |
|---|---|---|
| `text` | создано и прочитано | Базовый текст для кода/названия; нужен понятный label и подсказка. |
| `number` | создано и прочитано | Числа читаются в table view; точность задавать в `settings` по задаче. |
| `date` | создано и прочитано | Единственный тип, для которого разрешена постоянная нижняя сноска в форме. |
| `boolean` | создано и прочитано | Использовать для признаков; в списке скрывать, если не помогает решению пользователя. |
| `list` single | создано | Для статусов/типов обработки; значения должны быть читаемыми. |
| `list` multiple | создано | Проверять отображение отдельно: наличия поля во view недостаточно. |
| `ref source=view` | создано и использовано | Подходит для выбора из отфильтрованного справочного представления. |
| `ref source=basic` | создано | Подходит для прямой связи с типом материала, но читаемый вывод требует настройки view или join. |
| `file` | создано | Для вложений; в list view обычно скрывать, на форме давать понятный блок "Файлы". |
| `geo` | создано и использовано | Использовать для `leaflet`; после добавления во view читать реальный view-field `mname`. |

## Связи и relation views

Проверенный рабочий паттерн:

1. Создать справочник и reference view.
2. Создать основной тип материала с `ref`-полем.
3. Для `ref source=view` указать source view и content type источника.
4. Для пользовательского списка не выводить технический id как основной смысл.
5. Если нужно показать атрибут связанной записи, создать joined table view.
6. Join строить по фактическим view-field mname:
   - слева mname `ref`-поля;
   - справа `_id` связанной сущности, если backend добавил alias `_id0`, использовать именно его.
7. Проверить и `get-data`, и `get-data-simplified`.

Важное ограничение: длинные автоматически сгенерированные mname могут приводить
к SQL-неоднозначности из-за усечения имени колонки. Для типов материалов, где
планируются связи и joined views, нужно заранее задавать короткий `fieldNamePrefix`
и короткие suffix.

Если у content type задан `fieldNamePrefix`, в create-field нужно передавать
короткий suffix, а не уже полностью сгенерированный mname. Иначе backend может
добавить префикс повторно.

## View-field contract

Для системных атрибутов есть различие между add и save:

```json
{
  "entityId": "<view-entity-id>",
  "attribute": "_id"
}
```

```json
{
  "id": "<view-field-id>",
  "entityId": "<view-entity-id>",
  "contentTypeId": "<entity-content-type-id>",
  "contentAttribute": "_id",
  "settings": {}
}
```

MCP должен удалять null selector keys из save payload и не пытаться сохранять
`_id` как обычное content field mname.

## Правила для будущих сценариев

- Тип материала всегда получает описание, назначение и пользовательскую подсказку.
- Новые представления создаются в experimental/v2, кроме явно доказанных исключений.
- Для связей заранее проектируются короткие mname.
- Видимое имя связанной записи проверяется через view data, а не по факту сохранения поля.
- Встроенная форма/list surface должна иметь field-based filter или `dataId: [openId]`.
- В list view скрываются технические, пустые и неинформативные столбцы.
- Bottom helper text под полем используется только для `date`.
- После изменения представления обязательны readback populated fields и smoke через view data.

## Открытые пункты

- Для `calendar` нужен UI/HAR или отдельный route, который сохраняет `startDate/endDate`.
- Нужна отдельная серия по advanced `calc`, `spreadsheet`, `comb`, `address`,
  `bank`, `legal_entity`, `person` с UI-проверкой редактора.
- Запущенный MCP-процесс нужно перезапускать после изменения schema/tools, иначе
  live tool output может идти по старой схеме и старому redaction.
