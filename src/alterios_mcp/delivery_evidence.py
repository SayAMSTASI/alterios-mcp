from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Mapping, Sequence
from urllib.parse import unquote, urlparse

from .gitea_workboard import GiteaRequestError


ROLE_ALIASES: dict[str, frozenset[str]] = {
    "analyst": frozenset(
        {
            "analyst",
            "business analyst",
            "business/system analyst",
            "requirements analyst",
            "business-analyst",
            "business_analyst",
            "ba",
            "аналитик",
            "бизнес аналитик",
            "бизнес-аналитик",
            "аналитик требований",
        }
    ),
    "implementer": frozenset(
        {
            "implementer",
            "developer",
            "engineer",
            "implementation engineer",
            "profile engineer",
            "dev",
            "executor",
            "исполнитель",
            "разработчик",
        }
    ),
    "verifier": frozenset(
        {
            "verifier",
            "tester",
            "qa",
            "reviewer",
            "safety verifier",
            "тестировщик",
            "проверяющий",
        }
    ),
    "pm": frozenset(
        {
            "pm",
            "project manager",
            "project-manager",
            "project_manager",
            "manager",
            "проектный менеджер",
            "руководитель проекта",
        }
    ),
}

SECTION_ALIASES: dict[str, frozenset[str]] = {
    "role": frozenset({"agent", "роль"}),
    "scope": frozenset({"scope", "область"}),
    "inputs": frozenset({"inputs", "входные данные"}),
    "findings": frozenset({"findings", "result", "выводы", "что сделано"}),
    "artifacts": frozenset({"artifacts", "артефакты"}),
    "verification": frozenset({"verification", "проверка"}),
    "risks": frozenset({"risks", "риски"}),
    "next": frozenset({"next", "следующий шаг"}),
}

_WORK_ITEM_RE = re.compile(r"^gitea:#(?P<issue>[1-9]\d*)$", re.IGNORECASE)
_ROLE_HANDOFF_RE = re.compile(
    r"^gitea:#(?P<issue>[1-9]\d*)/comment/(?P<role>[^/?#]+)$",
    re.IGNORECASE,
)
_COMMENT_ID_RE = re.compile(
    r"^(?:(?:gitea:)?comment(?:/|:)|#?issuecomment-)?(?P<comment>[1-9]\d*)$",
    re.IGNORECASE,
)
_ISSUE_PATH_RE = re.compile(r"/issues/(?P<issue>[1-9]\d*)(?:/comments/(?P<comment>[1-9]\d*))?", re.IGNORECASE)
_COMMENT_PATH_RE = re.compile(r"/issues/comments/(?P<comment>[1-9]\d*)", re.IGNORECASE)
_COMMENT_FRAGMENT_RE = re.compile(r"(?:^|[-_/])(?:issue)?comment[-_/]?(?P<comment>[1-9]\d*)", re.IGNORECASE)


@dataclass(frozen=True)
class HandoffReference:
    kind: str
    issue_number: int | None = None
    comment_id: int | None = None
    role: str | None = None


def parse_work_item_ref(value: str) -> int:
    match = _WORK_ITEM_RE.fullmatch(str(value).strip())
    if not match:
        raise ValueError("work item reference must use gitea:#N format")
    return int(match.group("issue"))


def parse_handoff_ref(value: str) -> HandoffReference:
    normalized = str(value).strip()
    role_match = _ROLE_HANDOFF_RE.fullmatch(normalized)
    if role_match:
        role = canonical_role(unquote(role_match.group("role")))
        if role is None:
            raise ValueError("handoff role is not a supported role alias")
        return HandoffReference(
            kind="role",
            issue_number=int(role_match.group("issue")),
            role=role,
        )

    id_match = _COMMENT_ID_RE.fullmatch(normalized)
    if id_match:
        return HandoffReference(kind="comment_id", comment_id=int(id_match.group("comment")))

    parsed = urlparse(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("handoff reference must be gitea:#N/comment/<role>, a comment URL, or a comment id")

    issue_number: int | None = None
    comment_id: int | None = None
    issue_match = _ISSUE_PATH_RE.search(parsed.path)
    if issue_match:
        issue_number = int(issue_match.group("issue"))
        if issue_match.group("comment"):
            comment_id = int(issue_match.group("comment"))
    if comment_id is None:
        comment_path_match = _COMMENT_PATH_RE.search(parsed.path)
        if comment_path_match:
            comment_id = int(comment_path_match.group("comment"))
    if comment_id is None:
        fragment_match = _COMMENT_FRAGMENT_RE.search(parsed.fragment)
        if fragment_match:
            comment_id = int(fragment_match.group("comment"))
    if comment_id is None:
        raise ValueError("comment URL does not contain a comment identifier")
    return HandoffReference(kind="url", issue_number=issue_number, comment_id=comment_id)


def canonical_role(value: str) -> str | None:
    normalized = _normalize_token(value)
    for canonical, aliases in ROLE_ALIASES.items():
        if normalized == canonical or normalized in {_normalize_token(alias) for alias in aliases}:
            return canonical
    return None


def parse_handoff_comment(body: str) -> dict[str, str]:
    alias_map = {
        _normalize_label(alias): section
        for section, aliases in SECTION_ALIASES.items()
        for alias in aliases
    }
    parsed: dict[str, list[str]] = {}
    active_section: str | None = None
    for raw_line in str(body).splitlines():
        line = raw_line.strip()
        field = _split_field_line(line, alias_map)
        if field is not None:
            active_section, value = field
            parsed.setdefault(active_section, [])
            if value:
                parsed[active_section].append(value)
            continue
        if active_section and line:
            parsed[active_section].append(line)
    return {key: "\n".join(values).strip() for key, values in parsed.items()}


def validate_delivery_evidence(
    *,
    client: Any,
    work_item_ref: str,
    handoff_refs: Sequence[str],
    required_roles: Sequence[str],
    allow_closed: bool = False,
) -> dict[str, Any]:
    blockers: list[dict[str, Any]] = []
    issue_number: int | None = None
    issue_state: str | None = None
    required = _canonicalize_required_roles(required_roles, blockers)
    parsed_refs: list[HandoffReference] = []

    try:
        issue_number = parse_work_item_ref(work_item_ref)
    except ValueError as exc:
        blockers.append({"code": "invalid_work_item_ref", "message": str(exc)})

    if not handoff_refs:
        blockers.append({"code": "missing_handoff_refs"})
    for index, value in enumerate(handoff_refs):
        try:
            parsed_refs.append(parse_handoff_ref(value))
        except ValueError as exc:
            blockers.append(
                {
                    "code": "invalid_handoff_ref",
                    "ref_index": index,
                    "message": str(exc),
                }
            )

    if issue_number is not None:
        for reference in parsed_refs:
            if reference.issue_number is not None and reference.issue_number != issue_number:
                blockers.append(
                    {
                        "code": "mismatched_issue_ref",
                        "expected_issue_number": issue_number,
                        "actual_issue_number": reference.issue_number,
                    }
                )

    issue: Mapping[str, Any] | None = None
    if issue_number is not None:
        issue = _read_issue(client, issue_number, blockers)
        if issue is not None:
            response_issue_number = _positive_int(issue.get("number"))
            if response_issue_number is not None and response_issue_number != issue_number:
                blockers.append(
                    {
                        "code": "issue_response_mismatch",
                        "expected_issue_number": issue_number,
                        "actual_issue_number": response_issue_number,
                    }
                )
            issue_state = str(issue.get("state") or "").strip().lower() or None
            if issue_state == "closed" and not allow_closed:
                blockers.append(
                    {
                        "code": "closed_issue_not_allowed",
                        "issue_number": issue_number,
                    }
                )
            elif issue_state not in {"open", "closed"}:
                blockers.append(
                    {
                        "code": "unsupported_issue_state",
                        "issue_number": issue_number,
                        "state": issue_state,
                    }
                )

    comments: list[Mapping[str, Any]] = []
    if issue is not None and issue_number is not None:
        comments = _read_comments(client, issue_number, blockers)

    selected = _select_referenced_comments(parsed_refs, comments, issue_number, blockers)
    verified: list[tuple[str, int]] = []
    for comment in selected:
        comment_id = _positive_int(comment.get("id"))
        fields = parse_handoff_comment(str(comment.get("body") or ""))
        missing_sections = [name for name in SECTION_ALIASES if not fields.get(name)]
        if missing_sections:
            blockers.append(
                {
                    "code": "missing_handoff_sections",
                    "comment_id": comment_id,
                    "sections": missing_sections,
                }
            )
            continue
        role = canonical_role(fields["role"])
        if role is None:
            blockers.append(
                {
                    "code": "unsupported_handoff_role",
                    "comment_id": comment_id,
                }
            )
            continue
        if comment_id is None:
            blockers.append({"code": "missing_comment_id", "role": role})
            continue
        verified.append((role, comment_id))

    verified = sorted(set(verified), key=lambda item: (item[0], item[1]))
    verified_roles = sorted({role for role, _ in verified})
    missing_roles = sorted(set(required) - set(verified_roles))
    if missing_roles:
        blockers.append({"code": "missing_required_roles", "roles": missing_roles})

    receipt_core = {
        "schema_version": 1,
        "issue_number": issue_number,
        "issue_state": issue_state,
        "allow_closed": bool(allow_closed),
        "required_roles": required,
        "verified": [
            {"role": role, "comment_id": comment_id}
            for role, comment_id in verified
        ],
        "blockers": _stable_blockers(blockers),
    }
    fingerprint = hashlib.sha256(
        json.dumps(receipt_core, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return {
        "ok": not receipt_core["blockers"],
        "fingerprint_algorithm": "sha256",
        "fingerprint": fingerprint,
        "issue_number": issue_number,
        "issue_state": issue_state,
        "verified_roles": verified_roles,
        "verified_comment_ids": sorted({comment_id for _, comment_id in verified}),
        "blockers": receipt_core["blockers"],
    }


def _canonicalize_required_roles(
    values: Sequence[str],
    blockers: list[dict[str, Any]],
) -> list[str]:
    roles: list[str] = []
    for value in values:
        role = canonical_role(str(value))
        if role is None:
            blockers.append({"code": "unsupported_required_role"})
        else:
            roles.append(role)
    return sorted(set(roles))


def _read_issue(
    client: Any,
    issue_number: int,
    blockers: list[dict[str, Any]],
) -> Mapping[str, Any] | None:
    try:
        response = client.get_issue(issue_number)
    except GiteaRequestError as exc:
        code = "missing_issue" if exc.status_code == 404 else "issue_lookup_failed"
        blockers.append({"code": code, "issue_number": issue_number, "status_code": exc.status_code})
        return None
    except Exception:
        blockers.append({"code": "issue_lookup_failed", "issue_number": issue_number})
        return None
    if getattr(response, "status_code", 200) == 404:
        blockers.append({"code": "missing_issue", "issue_number": issue_number, "status_code": 404})
        return None
    body = getattr(response, "body", None)
    if not isinstance(body, Mapping):
        blockers.append({"code": "invalid_issue_response", "issue_number": issue_number})
        return None
    return body


def _read_comments(
    client: Any,
    issue_number: int,
    blockers: list[dict[str, Any]],
) -> list[Mapping[str, Any]]:
    try:
        response = client.list_issue_comments(issue_number)
    except Exception:
        blockers.append({"code": "comment_lookup_failed", "issue_number": issue_number})
        return []
    body = getattr(response, "body", None)
    if not isinstance(body, list):
        blockers.append({"code": "invalid_comments_response", "issue_number": issue_number})
        return []
    return [item for item in body if isinstance(item, Mapping)]


def _select_referenced_comments(
    references: Sequence[HandoffReference],
    comments: Sequence[Mapping[str, Any]],
    issue_number: int | None,
    blockers: list[dict[str, Any]],
) -> list[Mapping[str, Any]]:
    by_id = {
        comment_id: comment
        for comment in comments
        if (comment_id := _positive_int(comment.get("id"))) is not None
    }
    by_role: dict[str, list[Mapping[str, Any]]] = {}
    for comment in comments:
        role = canonical_role(parse_handoff_comment(str(comment.get("body") or "")).get("role", ""))
        if role:
            by_role.setdefault(role, []).append(comment)

    selected: dict[int, Mapping[str, Any]] = {}
    for reference in references:
        if issue_number is not None and reference.issue_number not in {None, issue_number}:
            continue
        comment: Mapping[str, Any] | None = None
        if reference.comment_id is not None:
            comment = by_id.get(reference.comment_id)
        elif reference.role is not None:
            candidates = by_role.get(reference.role, [])
            if candidates:
                comment = max(candidates, key=lambda item: _positive_int(item.get("id")) or 0)
        if comment is None:
            blocker: dict[str, Any] = {"code": "handoff_comment_not_found"}
            if reference.comment_id is not None:
                blocker["comment_id"] = reference.comment_id
            if reference.role is not None:
                blocker["role"] = reference.role
            blockers.append(blocker)
            continue
        comment_id = _positive_int(comment.get("id"))
        if comment_id is not None:
            selected[comment_id] = comment
    return [selected[key] for key in sorted(selected)]


def _split_field_line(line: str, alias_map: Mapping[str, str]) -> tuple[str, str] | None:
    if not line:
        return None
    cleaned = re.sub(r"^\s*(?:[-*+]\s+|#{1,6}\s*)", "", line).strip()
    cleaned = cleaned.replace("**", "").replace("__", "").strip()
    if ":" in cleaned:
        label, value = cleaned.split(":", 1)
    else:
        label, value = cleaned, ""
    section = alias_map.get(_normalize_label(label))
    if section is None:
        return None
    return section, value.strip()


def _normalize_label(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().casefold())


def _normalize_token(value: str) -> str:
    return re.sub(r"[\s_-]+", " ", str(value).strip().casefold())


def _positive_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and value > 0:
        return value
    if isinstance(value, str) and value.strip().isdigit() and int(value.strip()) > 0:
        return int(value.strip())
    return None


def _stable_blockers(blockers: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    unique = {
        json.dumps(dict(blocker), ensure_ascii=False, sort_keys=True, separators=(",", ":")): dict(blocker)
        for blocker in blockers
    }
    return [unique[key] for key in sorted(unique)]
