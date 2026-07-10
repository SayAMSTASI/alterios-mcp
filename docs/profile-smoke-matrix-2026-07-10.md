# Матрица smoke-проверки профилей

- Сформировано: `2026-07-10T09:30:23+00:00`
- Read-only run: `True`
- Write gate включен в окружении: `False`
- Project IDs включены: `False`
- Project names включены: `False`

## Сводка

| Метрика | Значение |
|---|---:|
| Всего профилей | 2 |
| Instance project lists OK | 2 |
| Default project discovery OK | 2 |
| Default project discovery skipped | 0 |
| Всего найдено проектов | 53 |

## Профили

| Profile | Token | Base URL | Default project | Projects | Default route smoke |
|---|---|---|---|---:|---|
| artx | <set> | <set> | <set> | 35 | 15/15 OK |
| vniimt | <set> | <set> | <set> | 18 | 15/15 OK |

## Ошибки и пропуски

- Failed checks нет. Project-scoped discovery может быть пропущен, если у
  профиля не задан default project id.

## Примечания

- Runner вызывает только read-only inventory routes.
- Tokens, auth headers, private dotenv contents и base URLs не записываются в
  этот artifact.
- Project IDs и names не включаются, пока runner не вызван с
  `--include-project-ids` или `--include-project-names`.
