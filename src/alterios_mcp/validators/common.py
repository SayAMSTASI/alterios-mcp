"""Pure configuration and expected-entity validators."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any


ALTERIOS_SCRIPT_TYPES = {"web", "cron", "manual", "event", "library", "diagram"}
MANAGED_MARKER = "Codex-managed"

def _validate_script_type_config(script_type: str, config: dict[str, Any]) -> None:
    if script_type not in ALTERIOS_SCRIPT_TYPES:
        allowed = ", ".join(sorted(ALTERIOS_SCRIPT_TYPES))
        raise ValueError(f"script_type must be one of: {allowed}.")
    if script_type != "cron":
        return
    cron = config.get("cron")
    if not isinstance(cron, str) or not cron.strip():
        raise ValueError("cron script requires config.cron as a six-part string: second minute hour day month week.")
    if len(cron.split()) != 6:
        raise ValueError("cron script config.cron must contain six parts: second minute hour day month week.")

def _assert_expected_content(
    content: dict[str, Any],
    *,
    expected_content_type_id: str | None = None,
    expected_name: str | None = None,
) -> None:
    if expected_content_type_id and content.get("contentTypeId") != expected_content_type_id:
        raise ValueError(
            f"Content type mismatch: expected {expected_content_type_id!r}, got {content.get('contentTypeId')!r}."
        )
    if expected_name and content.get("name") != expected_name:
        raise ValueError(f"Content name mismatch: expected {expected_name!r}, got {content.get('name')!r}.")

def _normalize_google_icon_svg(text: str, *, size: int, color: str) -> bytes:
    if "<svg" not in text or "</svg>" not in text:
        raise ValueError("Google icon response is not an SVG.")
    match = re.search(r"<svg\b([^>]*)>", text, flags=re.IGNORECASE)
    if not match:
        raise ValueError("SVG root element was not found.")
    attrs = match.group(1)
    attrs = re.sub(r'\s(?:width|height|fill)="[^"]*"', "", attrs, flags=re.IGNORECASE)
    if "viewBox=" not in attrs:
        attrs += ' viewBox="0 -960 960 960"'
    if "xmlns=" not in attrs:
        attrs += ' xmlns="http://www.w3.org/2000/svg"'
    render_size = 20 if size == 16 else size
    replacement = f'<svg{attrs} width="{render_size}px" height="{render_size}px" fill="{color}">'
    normalized = text[: match.start()] + replacement + text[match.end() :]
    return normalized.encode("utf-8")

def _downloaded_icon_payload_valid(data: bytes, *, filename: str, content_type: str) -> bool:
    if not data:
        return False
    prefix = data[:512].lstrip().lower()
    if prefix.startswith(b"<!doctype html") or prefix.startswith(b"<html") or b"<html" in prefix[:128]:
        return False
    suffix = Path(filename).suffix.lower()
    if suffix == ".svg" or "svg" in content_type.lower():
        return b"<svg" in prefix or b"<svg" in data[:4096].lower()
    return True

def _assert_managed_or_allowed(resource: dict[str, Any], *, kind: str, allow_unmanaged_update: bool) -> None:
    if allow_unmanaged_update:
        return
    if MANAGED_MARKER in str(resource.get("description") or ""):
        return
    raise ValueError(f"{kind} {resource.get('_id')!r} is not marked as Codex-managed; pass allow_unmanaged_update=True.")

def _assert_help_managed_or_allowed(resource: dict[str, Any], *, allow_unmanaged_update: bool) -> None:
    if allow_unmanaged_update:
        return
    if MANAGED_MARKER in str(resource.get("description") or "") or MANAGED_MARKER in str(resource.get("value") or ""):
        return
    raise ValueError(f"Help {resource.get('_id')!r} is not marked as Codex-managed; pass allow_unmanaged_update=True.")

def _assert_expected_task(
    task: dict[str, Any],
    *,
    expected_process_id: str | None = None,
    expected_content_id: str | None = None,
    expected_diagram_id: str | None = None,
) -> None:
    expected = {
        "processId": expected_process_id,
        "contentId": expected_content_id,
        "diagramId": expected_diagram_id,
    }
    for key, value in expected.items():
        if value and task.get(key) != value:
            raise ValueError(f"Task {task.get('_id')!r} {key} mismatch: expected {value!r}, got {task.get(key)!r}.")

def _normalize_process_script_refs(script_refs: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    if script_refs is None:
        return []
    if not isinstance(script_refs, list):
        raise ValueError("script_refs must be a list.")
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, raw in enumerate(script_refs):
        if not isinstance(raw, dict):
            raise ValueError("Each script ref must be a JSON object.")
        script_id = str(raw.get("script_id") or raw.get("scriptId") or raw.get("_id") or "").strip()
        name = str(raw.get("name") or "").strip() or None
        script_type = str(raw.get("type") or raw.get("script_type") or "diagram").strip()
        expected_body_contains = raw.get("expected_body_contains") or raw.get("expectedBodyContains") or []
        if isinstance(expected_body_contains, str):
            expected_body_contains = [expected_body_contains]
        if not script_id and not name:
            raise ValueError(f"script_refs[{index}] requires script_id or name.")
        if script_type not in {"manual", "event", "diagram"}:
            raise ValueError("script_refs[].type must be one of: manual, event, diagram.")
        key = script_id or name or str(index)
        if key in seen:
            raise ValueError(f"Duplicate script ref {key!r}.")
        seen.add(key)
        normalized.append(
            {
                "script_id": script_id or None,
                "name": name,
                "type": script_type,
                "expected_body_contains": [str(item) for item in expected_body_contains],
            }
        )
    return normalized

__all__ = ['_validate_script_type_config', '_assert_expected_content', '_normalize_google_icon_svg', '_downloaded_icon_payload_valid', '_assert_managed_or_allowed', '_assert_help_managed_or_allowed', '_assert_expected_task', '_normalize_process_script_refs']
