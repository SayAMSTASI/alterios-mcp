from __future__ import annotations

from typing import Any


UX_CONTRACT_VERSION = "2026-07-16.2"

BLOCKING_FORM_ISSUE_CODES = frozenset(
    {
        "add_edit_page_action_order",
        "close_action_missing_redirect_back",
        "element_action_title_must_be_tooltip",
        "embedded_view_missing_filter_or_context",
        "field_footnote_requires_date",
        "list_row_action_icon_missing",
        "list_row_actions_must_be_menu",
        "list_row_menu_actions_missing",
        "missing_page_title",
        "non_table_cell_header",
        "report_or_analytics_form_should_open_new_tab",
        "report_or_analytics_target_missing_close",
        "row_menu_default_view_missing",
        "table_cell_header_style",
        "technical_list_field_must_be_hidden",
        "view_detail_close_action_missing",
        "view_detail_view_data_must_be_readonly",
    }
)


def apply_form_contract(issues: list[dict[str, Any]], *, strict: bool) -> list[dict[str, Any]]:
    """Promote confirmed Alterios UX violations to errors in strict mode."""
    normalized: list[dict[str, Any]] = []
    for issue in issues:
        item = dict(issue)
        if strict and item.get("code") in BLOCKING_FORM_ISSUE_CODES:
            item["severity"] = "error"
            item["contract_version"] = UX_CONTRACT_VERSION
        normalized.append(item)
    return normalized


def assert_form_contract(surface: dict[str, Any]) -> None:
    errors = [issue for issue in surface.get("issues", []) if issue.get("severity") == "error"]
    if not errors:
        return
    summary = ", ".join(
        f"{issue.get('code')} at {issue.get('path')}" for issue in errors[:8]
    )
    raise ValueError(f"Alterios UX contract {UX_CONTRACT_VERSION} failed: {summary}")
