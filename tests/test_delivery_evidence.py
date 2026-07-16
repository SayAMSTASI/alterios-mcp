from __future__ import annotations

from typing import Any

from alterios_mcp.delivery_evidence import (
    parse_handoff_ref,
    parse_work_item_ref,
    validate_delivery_evidence,
)
from alterios_mcp.gitea_workboard import GiteaClient, GiteaConfig


class FakeResponse:
    def __init__(self, body: Any, status_code: int = 200) -> None:
        self.body = body
        self.status_code = status_code


class FakeClient:
    def __init__(self, issue: dict[str, Any] | None, comments: list[dict[str, Any]]) -> None:
        self.issue = issue
        self.comments = comments
        self.issue_reads: list[int] = []
        self.comment_reads: list[int] = []

    def get_issue(self, issue_number: int) -> FakeResponse:
        self.issue_reads.append(issue_number)
        if self.issue is None:
            return FakeResponse({"message": "not found"}, status_code=404)
        return FakeResponse(self.issue)

    def list_issue_comments(self, issue_number: int) -> FakeResponse:
        self.comment_reads.append(issue_number)
        return FakeResponse(self.comments)


def handoff(comment_id: int, role: str, *, omit: str | None = None) -> dict[str, Any]:
    sections = {
        "role": f"Agent: {role}",
        "scope": "Scope: Implement the assigned delivery slice",
        "inputs": "Inputs: work item and source files",
        "findings": "Findings: implementation completed",
        "artifacts": "Артефакты: source and tests",
        "verification": "Проверка: pytest passed",
        "risks": "Риски: none",
        "next": "Следующий шаг: hand off",
    }
    if omit:
        sections.pop(omit)
    return {"id": comment_id, "body": "\n".join(sections.values())}


def validate(
    client: FakeClient,
    *,
    refs: list[str],
    roles: list[str],
    work_item_ref: str = "gitea:#42",
    allow_closed: bool = False,
) -> dict[str, Any]:
    return validate_delivery_evidence(
        client=client,
        work_item_ref=work_item_ref,
        handoff_refs=refs,
        required_roles=roles,
        allow_closed=allow_closed,
    )


def blocker_codes(result: dict[str, Any]) -> set[str]:
    return {item["code"] for item in result["blockers"]}


def test_delivery_evidence_success_and_stable_fingerprint() -> None:
    client = FakeClient(
        {"number": 42, "state": "open", "title": "Private delivery"},
        [
            handoff(101, "Аналитик"),
            handoff(102, "Developer"),
            handoff(103, "QA"),
            handoff(104, "Project Manager"),
        ],
    )
    refs = [
        "gitea:#42/comment/analyst",
        "102",
        "https://gitea.example/owner/repo/issues/42#issuecomment-103",
        "comment:104",
    ]

    result = validate(client, refs=refs, roles=["ANALYST", "implementer", "Verifier", "PM"])
    repeated = validate(client, refs=refs, roles=["pm", "verifier", "implementer", "analyst"])

    assert result["ok"] is True
    assert result["issue_number"] == 42
    assert result["verified_roles"] == ["analyst", "implementer", "pm", "verifier"]
    assert result["verified_comment_ids"] == [101, 102, 103, 104]
    assert result["blockers"] == []
    assert result["fingerprint_algorithm"] == "sha256"
    assert len(result["fingerprint"]) == 64
    assert result["fingerprint"] == repeated["fingerprint"]


def test_delivery_evidence_blocks_missing_issue() -> None:
    client = FakeClient(None, [])

    result = validate(client, refs=["gitea:#42/comment/analyst"], roles=["analyst"])

    assert result["ok"] is False
    assert "missing_issue" in blocker_codes(result)
    assert client.comment_reads == []


def test_delivery_evidence_blocks_empty_handoff_refs() -> None:
    client = FakeClient({"number": 42, "state": "open"}, [])

    result = validate(client, refs=[], roles=[])

    assert result["ok"] is False
    assert "missing_handoff_refs" in blocker_codes(result)


def test_delivery_evidence_blocks_mismatched_issue_reference() -> None:
    client = FakeClient({"number": 42, "state": "open"}, [handoff(101, "analyst")])

    result = validate(client, refs=["gitea:#43/comment/analyst"], roles=["analyst"])

    assert result["ok"] is False
    assert "mismatched_issue_ref" in blocker_codes(result)


def test_delivery_evidence_blocks_missing_comment_sections() -> None:
    client = FakeClient({"number": 42, "state": "open"}, [handoff(101, "analyst", omit="risks")])

    result = validate(client, refs=["101"], roles=["analyst"])

    assert result["ok"] is False
    assert "missing_handoff_sections" in blocker_codes(result)
    blocker = next(item for item in result["blockers"] if item["code"] == "missing_handoff_sections")
    assert blocker["sections"] == ["risks"]


def test_delivery_evidence_requires_findings_and_inputs() -> None:
    client = FakeClient({"number": 42, "state": "open"}, [handoff(101, "analyst", omit="findings")])

    result = validate(client, refs=["101"], roles=["analyst"])

    blocker = next(item for item in result["blockers"] if item["code"] == "missing_handoff_sections")
    assert blocker["sections"] == ["findings"]


def test_delivery_evidence_blocks_missing_required_role() -> None:
    client = FakeClient({"number": 42, "state": "open"}, [handoff(101, "analyst")])

    result = validate(client, refs=["101"], roles=["analyst", "verifier"])

    assert result["ok"] is False
    blocker = next(item for item in result["blockers"] if item["code"] == "missing_required_roles")
    assert blocker["roles"] == ["verifier"]


def test_delivery_evidence_requires_explicit_closed_issue_permission() -> None:
    client = FakeClient({"number": 42, "state": "closed"}, [handoff(101, "pm")])

    blocked = validate(client, refs=["101"], roles=["pm"])
    allowed = validate(client, refs=["101"], roles=["pm"], allow_closed=True)

    assert blocked["ok"] is False
    assert "closed_issue_not_allowed" in blocker_codes(blocked)
    assert allowed["ok"] is True


def test_read_methods_use_repository_issue_endpoints_without_network() -> None:
    calls: list[tuple[str, str, dict[str, Any]]] = []

    class CaptureClient(GiteaClient):
        def _request(self, method: str, path: str, **kwargs: Any) -> FakeResponse:
            calls.append((method, path, kwargs))
            return FakeResponse([])

    client = CaptureClient(
        GiteaConfig(base_url="https://gitea.example", token="secret", owner="owner", repo="repo")
    )

    client.get_issue(42)
    client.list_issue_comments(42)

    assert calls == [
        ("GET", "/api/v1/repos/owner/repo/issues/42", {}),
        ("GET", "/api/v1/repos/owner/repo/issues/42/comments", {"params": {"limit": 100}}),
    ]
    assert parse_work_item_ref("gitea:#42") == 42
    assert parse_handoff_ref("https://gitea.example/owner/repo/issues/42#issuecomment-101").comment_id == 101
