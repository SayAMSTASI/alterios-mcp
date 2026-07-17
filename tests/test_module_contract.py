from __future__ import annotations

import time
from types import SimpleNamespace
from unittest.mock import patch

from alterios_mcp._support import _material_module_plan_preview, _normalize_material_module_fields
from alterios_mcp.scenarios import content as content_scenarios
from alterios_mcp.scenarios import views_forms as view_scenarios
from alterios_mcp.validators.module_contract import validate_icon_svg, validate_module_contract


SVG = '<svg xmlns="http://www.w3.org/2000/svg" width="20px" height="20px" viewBox="0 -960 960 960" fill="#4B77D1"><path d="M0 0"/></svg>'


ICON_IDS = {
    "module": "00000000-0000-4000-8000-000000000001",
    "add": "00000000-0000-4000-8000-000000000002",
    "edit": "00000000-0000-4000-8000-000000000003",
    "view": "00000000-0000-4000-8000-000000000004",
    "delete": "00000000-0000-4000-8000-000000000005",
    "menu": "00000000-0000-4000-8000-000000000006",
    "close": "00000000-0000-4000-8000-000000000007",
    "save": "00000000-0000-4000-8000-000000000008",
}


def _valid_module() -> tuple[dict[str, object], dict[str, str]]:
    fields = _normalize_material_module_fields(
        [{"name": "Наименование", "mname": "mat_name", "field_type": "text"}],
        field_name_prefix="mat",
    )
    names = {
        "content_type": "Показатель",
        "view": "Показатели. Список",
        "add_form": "Показатели. Добавить",
        "edit_form": "Показатель. Редактирование",
        "view_form": "Показатель. Просмотр",
        "list_form": "Показатели",
        "group": "Показатели",
        "add_page_title": "Добавить показатель",
        "edit_page_title": "Показатель",
        "view_page_title": "Показатель",
        "list_page_title": "Показатели",
    }
    preview = _material_module_plan_preview(
        module_name="Показатель",
        names=names,
        fields=fields,
        field_name_prefix="mat",
        content_type_id="ct-1",
        view_id="view-1",
        add_form_id="form-add",
        edit_form_id="form-edit",
        view_form_id="form-view",
        list_form_id="form-list",
        group_id="group-1",
        parent_group_id=None,
        icon_id=ICON_IDS["module"],
        add_icon_id=ICON_IDS["add"],
        edit_icon_id=ICON_IDS["edit"],
        view_icon_id=ICON_IDS["view"],
        delete_icon_id=ICON_IDS["delete"],
        menu_icon_id=ICON_IDS["menu"],
        close_icon_id=ICON_IDS["close"],
        save_icon_id=ICON_IDS["save"],
    )
    forms = {
        role: {
            "name": form["name"],
            "pageTitle": form["page_title"],
            "tabs": form["tabs"],
            "formActionContainers": form["formActionContainers"],
        }
        for role, form in preview["forms"].items()
    }
    semantics = {
        "module": "category",
        "add": "add_2",
        "edit": "edit",
        "view": "preview",
        "delete": "delete",
        "menu": "more_vert",
        "close": "keyboard_return",
        "save": "save",
    }
    registry = {
        "icons": {
            semantic: {
                "semantic": google_name,
                "google_name": google_name,
                "file_id": ICON_IDS[semantic],
                "size": 16,
                "render_size": 20,
                "color": "#4B77D1",
                "file_contract_verified": True,
            }
            for semantic, google_name in semantics.items()
        }
    }
    module = {
        "content_type": {"_id": "ct-1", "name": "Показатель", "description": "Справочник измеряемых показателей."},
        "fields": fields,
        "view": preview["view"],
        "view_entities": [preview["view"]["entity"]],
        "view_fields": [{"mname": "_id", "alias": "ID"}, {"mname": "name", "alias": "Наименование"}],
        "forms": forms,
        "reports": [],
        "group": preview["group"],
        "icon_registry": registry,
    }
    payloads = {file_id: SVG for file_id in ICON_IDS.values()}
    return module, payloads


def test_complete_module_contract_accepts_reference_material_module() -> None:
    module, payloads = _valid_module()

    result = validate_module_contract(module, icon_payloads=payloads)

    assert result["ok"] is True
    assert result["blocking_issue_count"] == 0
    assert result["inventory"]["icons"]["file_verified_count"] == 8


def test_module_contract_blocks_description_action_parity_and_icon_file_contract() -> None:
    module, payloads = _valid_module()
    module["content_type"]["description"] = "Codex-managed"
    edit_cell = module["forms"]["edit"]["tabs"][0]["rows"][0]["cells"][0]
    edit_cell["cellActionContainers"] = [
        {
            "type": "action",
            "title": "",
            "tooltip": "Печать",
            "iconId": ICON_IDS["view"],
            "actions": [{"type": "forms"}],
        }
    ]
    payloads[ICON_IDS["save"]] = SVG.replace('width="20px"', 'width="24px"')

    result = validate_module_contract(module, icon_payloads=payloads)

    assert result["ok"] is False
    assert result["blocking_issues_by_code"]["content_type_description_missing"] == 1
    assert result["blocking_issues_by_code"]["view_edit_element_actions_mismatch"] == 1
    assert result["blocking_issues_by_code"]["icon_file_size_mismatch"] >= 1


def test_icon_svg_contract_distinguishes_google_source_size_from_render_canvas() -> None:
    assert validate_icon_svg(SVG)["ok"] is True
    assert validate_icon_svg(SVG.replace("#4B77D1", "#000000"))["ok"] is False
    assert validate_icon_svg(SVG.replace('height="20px"', 'height="16px"'))["ok"] is False


def test_module_contract_covers_bulk_relations_and_report_sources() -> None:
    module, payloads = _valid_module()
    module["view_entities"].append({"name": "Связанные значения", "config": {"main": False}})
    module["reports"] = [{"name": "Печатная форма", "template": {"Pages": []}}]

    result = validate_module_contract(module, require_bulk_interface=True, icon_payloads=payloads)

    assert result["blocking_issues_by_code"]["bulk_interface_missing"] == 1
    assert result["blocking_issues_by_code"]["relation_join_missing"] == 1
    assert result["blocking_issues_by_code"]["report_source_missing"] == 1


def test_offline_module_contract_has_small_cpu_cost() -> None:
    module, payloads = _valid_module()
    started = time.perf_counter()
    for _ in range(100):
        result = validate_module_contract(module, icon_payloads=payloads)
        assert result["ok"] is True
    elapsed = time.perf_counter() - started

    assert elapsed < 2.0


def test_live_module_contract_uses_nine_exact_reads_and_no_icon_downloads() -> None:
    module, _ = _valid_module()

    class Response:
        def __init__(self, body: object) -> None:
            self.body = body

    class Client:
        def __init__(self) -> None:
            self.config = SimpleNamespace(profile="test", project_id="project-1")
            self.calls = 0

        def _response(self, body: object) -> Response:
            self.calls += 1
            return Response(body)

        def content_type_by_id(self, resource_id: str) -> Response:
            return self._response(module["content_type"])

        def list_fields(self, **_: object) -> Response:
            return self._response(module["fields"])

        def view_by_id(self, resource_id: str) -> Response:
            return self._response(module["view"])

        def view_entities(self, resource_id: str) -> Response:
            return self._response(module["view_entities"])

        def view_fields_populated(self, resource_id: str) -> Response:
            return self._response(module["view_fields"])

        def form_by_id(self, resource_id: str) -> Response:
            role = resource_id.removeprefix("form-")
            return self._response(module["forms"][role])

        def download_file(self, resource_id: str) -> tuple[bytes, str]:
            raise AssertionError("Default module validation must not download icon files.")

    client = Client()
    with (
        patch.object(view_scenarios, "_client", return_value=client),
        patch.object(view_scenarios, "_read_project_icon_registry", return_value=module["icon_registry"]),
        patch.object(view_scenarios, "_module_local_icon_payloads", return_value={}),
    ):
        result = view_scenarios.alterios_validate_module_contract(
            content_type_id="ct-1",
            view_id="view-1",
            add_form_id="form-add",
            edit_form_id="form-edit",
            view_form_id="form-view",
            list_form_id="form-list",
        )

    assert result["ok"] is True
    assert result["load_profile"]["api_call_count"] == client.calls == 9
    assert result["load_profile"]["icon_download_count"] == 0
    assert result["load_profile"]["project_inventory_scan"] is False


def test_low_level_content_type_apply_blocks_missing_description() -> None:
    class Response:
        def __init__(self, body: object) -> None:
            self.body = body

    class Client:
        def list_content_types(self, **_: object) -> Response:
            return Response([[], 0])

        def save_content_type(self, payload: dict[str, object]) -> Response:
            raise AssertionError("Invalid content type must not be written.")

    with (
        patch.dict("os.environ", {"ALTERIOS_MCP_ALLOW_WRITE": "1"}, clear=True),
        patch.object(content_scenarios, "_client", return_value=Client()),
    ):
        dry_run = content_scenarios.alterios_upsert_content_type(
            "Показатель",
            field_name_prefix="metric",
            profile="test",
            project_id="project-1",
        )
        assert dry_run["response"]["module_contract"]["ok"] is False

        try:
            content_scenarios.alterios_upsert_content_type(
                "Показатель",
                field_name_prefix="metric",
                dry_run=False,
                profile="test",
                project_id="project-1",
            )
        except ValueError as exc:
            assert "content_type_description_missing" in str(exc)
        else:
            raise AssertionError("Missing content type description must block apply.")
