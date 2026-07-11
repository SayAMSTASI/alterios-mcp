---
name: alterios-field-types
description: Understand, explain, audit, and configure Alterios/LIMS content type fields. Use when choosing persisted field types, relation fields, list/file/date/ref/calc/spreadsheet/combined/person/address/bank/legal entity fields, field settings, material type descriptions, field hints, or when building views/forms whose source fields must be modeled correctly.
---

# Alterios Field Types

Use this skill when the work depends on persisted content type fields. Do not
confuse content type fields with view fields, form widgets, filters, or table
display cells.

## Workflow

1. Identify the target `profile`, `project_id`, content type, and whether the
   user asks about persisted data, display in a view, or a form widget.
2. Read existing fields for the target content type before writing.
3. Choose field types from the confirmed persisted type family:
   `text`, `number`, `boolean`, `date`, `list`, `ref`, `file`, `inc`, `calc`,
   `spreadsheet`, `comb`, `address`, `geo`, `bank`, `legal_entity`, `person`.
4. For every new material/content type, provide a meaningful description and
   user-facing hint. Do not leave purpose/help empty.
5. For relation work, design short field suffixes and `fieldNamePrefix` before
   creating fields; view joins can break when generated mnames are too long.
6. When `fieldNamePrefix` is set, pass short field suffixes to create-field; do
   not pass an already fully prefixed/generated mname, because the backend can
   prepend the prefix again.
7. After writes, verify actual returned `mname`, `type`, `settings`, form field
   binding, view field binding, and view data smoke.

## Key Rules

- Field type and UI widget are different layers. A `view_data_list`, table cell,
  report tab, or process list is not a persisted field type.
- Use bottom helper/footnote text under a field only for persisted `date` fields.
  For other fields use label, tooltip, placeholder, help block, or description.
- Use `person` when FIO needs structured surname/name/patronymic; use `text` for
  a simple free-form string.
- Use `ref` when the record stores a link to another content row.
- Use `comb` when the field displays a compact block of attributes from a
  selected source content type; avoid self-recursive combined fields without UI
  proof.
- Use `spreadsheet` for in-system editable cell data; use `file` for uploaded
  XLSX/CSV/documents.
- Use `geo` for persisted geographic objects that must be shown in `leaflet`
  views; attach it to the view, read the populated view-field `mname`, then use
  that mname in `settings.geoFields[].name`.
- Treat calculated fields as derived values; document expression, source mnames,
  and recalculation expectations.
- Preserve existing fields unless cleanup is explicitly requested and narrowly
  targeted by known ids/prefixes.

## Relation Patterns

For `ref source=view`:

- create or select a `reference` view for the lookup source;
- point settings to that view and source content type;
- verify the selector and direct view data readback.

For `ref source=basic`:

- point settings to the source content type;
- configure search/display fields where supported;
- expect direct table data to return ids/arrays unless the view is configured to
  show related attributes.

For readable relation lists and reports:

- create a joined `table` view in experimental/v2;
- read real view-field mnames before writing join conditions;
- join the local ref field to the related entity `_id` view-field alias;
- verify both `get-data` and `get-data-simplified`.

## References

Read `references/source-map.md` first, then open only the listed documents needed
for the current field family or relation scenario.
