"""Fresh, bounded checks of explicit objects and supported outgoing references.

This is not a project health certificate or an incoming-impact analysis.
"""
from __future__ import annotations

from collections import deque
from .client import AlteriosClient, AlteriosConfig, AlteriosRequestError
from .form_surface import analyze_form_surface
from .performance import measured
from .read_workflows import fingerprint, safe_payload

METHODS = {"forms": "form_full", "views": "view_full", "fields": "field_by_id",
           "content_types": "content_type_by_id", "scripts": "script_by_id",
           "reports": "report_by_id", "diagrams": "diagram_by_id"}
REFERENCES = {"formId": "forms", "viewId": "views", "contentTypeId": "content_types",
              "contentTypeFieldId": "fields", "scriptId": "scripts", "manualScriptId": "scripts",
              "librariesIds": "scripts", "reportId": "reports", "diagramId": "diagrams"}


def references(value, path=""):
    if isinstance(value, dict):
        for key, item in value.items():
            item_path = path + "/" + str(key)
            if key in REFERENCES and item not in (None, "", []):
                values = item if isinstance(item, list) else [item]
                for ref in values:
                    identity = ref.get("_id") if isinstance(ref, dict) else ref
                    yield REFERENCES[key], identity, item_path
            yield from references(item, item_path)
    elif isinstance(value, list):
        for i, item in enumerate(value):
            yield from references(item, path + "/" + str(i))


@measured
def run_scoped_health(*, profile, project_id, objects, max_objects=50, max_depth=3, client=None):
    if not profile.strip() or not project_id.strip() or not 1 <= max_objects <= 100 or not 0 <= max_depth <= 8:
        raise ValueError("Invalid scope target or budget")
    if not isinstance(objects, list) or not objects or len(objects) > max_objects:
        raise ValueError("A nonempty bounded objects list is required")
    roots = []
    for obj in objects:
        if not isinstance(obj, dict) or set(obj) != {"kind", "id"} or obj["kind"] not in METHODS:
            raise ValueError("Scope objects require supported kind and id only")
        if not isinstance(obj["id"], str) or not obj["id"].strip() or len(obj["id"]) > 256:
            raise ValueError("Invalid scoped object ID")
        roots.append((obj["kind"], obj["id"]))
    if client is None:
        client = AlteriosClient(AlteriosConfig.from_env(profile=profile).with_project_id(project_id))
    if client.config.profile != profile or client.config.project_id != project_id:
        raise ValueError("Client target does not match scope")
    queue = deque((kind, identity, 0) for kind, identity in dict.fromkeys(roots))
    scheduled = set(roots)
    loaded, errors, links = [], [], []
    while queue:
        kind, identity, depth = queue.popleft()
        if len(loaded) >= max_objects:
            errors.append({"code": "scope_object_limit"})
            break
        item = {"kind": kind, "id": identity, "depth": depth}
        loaded.append(item)
        try:
            body = getattr(client, METHODS[kind])(identity).body
            if not isinstance(body, dict) or str(body.get("_id") or body.get("id") or "") != identity:
                errors.append({"code": "scope_identity_mismatch", "kind": kind, "id": identity})
                continue
            if body.get("projectId") and body["projectId"] != project_id:
                errors.append({"code": "scope_project_mismatch", "kind": kind, "id": identity})
                continue
            if kind == "forms":
                analysis = analyze_form_surface(body, strict=True)
                violations = [issue for issue in analysis.get("issues", []) if issue.get("severity") == "error"]
                if violations:
                    errors.append({"code": "scoped_form_contract", "id": identity, "issues": violations})
            if kind == "views":
                body = {**body, "_scope_entities": client.view_entities(identity).body,
                        "_scope_fields": client.view_fields_populated(identity).body}
            item["fingerprint"] = fingerprint(body)
            for target_kind, target_id, path in references(body):
                if len(links) >= max_objects * 32:
                    errors.append({"code": "scope_reference_limit", "id": identity})
                    queue.clear()
                    break
                if not isinstance(target_id, str) or not target_id.strip() or len(target_id) > 256:
                    errors.append({"code": "invalid_reference", "id": identity, "path": path})
                    continue
                links.append({"source_kind": kind, "source_id": identity,
                              "target_kind": target_kind, "target_id": target_id, "path": path})
                target = (target_kind, target_id)
                if target in scheduled:
                    continue
                if depth >= max_depth or len(scheduled) >= max_objects:
                    errors.append({"code": "scope_dependency_limit", "id": identity, "path": path})
                    continue
                scheduled.add(target)
                queue.append((*target, depth + 1))
        except (AlteriosRequestError, ValueError, OSError) as exc:
            errors.append({"code": "scoped_read_failed", "kind": kind, "id": identity,
                           "error_type": type(exc).__name__})
    return safe_payload({"readonly": True, "source": "live", "scope": "explicit_objects_and_known_outgoing_references",
                         "target": {"profile": profile, "project_id": project_id}, "roots": objects,
                         "summary": {"ok": not errors, "object_count": len(loaded), "reference_count": len(links)},
                         "objects": loaded, "references": links, "errors": errors,
                         "complete_within_supported_scope": not errors, "full_project_verified": False,
                         "limitations": ["Incoming references, dynamic script/BPMN/report references, permissions and runtime business behavior are not verified.",
                                         "Supported references are literal structured ID keys; callers must add other known dependencies explicitly.",
                                         "A successful scoped result does not replace write gates or authorize destructive operations."]})
