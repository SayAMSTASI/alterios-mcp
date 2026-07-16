from __future__ import annotations

from typing import Any


UX_CONTRACT_VERSION = "2026-07-16.1"

BLOCKING_FORM_ISSUE_CODES = frozenset(
    {
        "close_action_missing_redirect_back",
        "element_action_title_must_be_tooltip",
        "field_footnote_requires_date",
        "non_table_cell_header",
        "table_cell_header_style",
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
