from __future__ import annotations

from unittest.mock import patch

import pytest

from alterios_mcp import server
from alterios_mcp.gitea_workboard import GiteaConfigError, load_standard_labels


class FakeGiteaResponse:
    def __init__(self, body: object, status_code: int = 200) -> None:
        self.status_code = status_code
        self.body = body

    def as_dict(self) -> dict[str, object]:
        return {"status_code": self.status_code, "content_type": "application/json", "body": self.body}


class FakeGiteaClient:
    created_issue_payload: dict[str, object] | None = None

    def __init__(self, _config: object) -> None:
        pass

    def resolve_label_ids(self, labels: list[str]) -> list[int]:
        assert labels == ["type:feature", "stage:build"]
        return [11, 12]

    def resolve_milestone_id(self, milestone: object) -> int:
        assert milestone == "2026-07-S1"
        return 21

    def create_issue(self, payload: dict[str, object]) -> FakeGiteaResponse:
        FakeGiteaClient.created_issue_payload = payload
        return FakeGiteaResponse({"number": 5, "title": payload["title"]}, status_code=201)


class FakeSprintClient:
    ensured: dict[str, object] | None = None
    listed: dict[str, object] | None = None

    def __init__(self, _config: object) -> None:
        pass

    def ensure_milestone(self, *, title: str, description: str = "", due_on: str | None = None, state: str = "open") -> dict[str, object]:
        FakeSprintClient.ensured = {
            "title": title,
            "description": description,
            "due_on": due_on,
            "state": state,
        }
        return {"created": True, "milestone": {"id": 7, "title": title}}

    def list_issues(
        self,
        *,
        state: str = "open",
        labels: list[str] | None = None,
        milestones: list[str] | None = None,
        query: str | None = None,
        limit: int = 20,
    ) -> FakeGiteaResponse:
        FakeSprintClient.listed = {
            "state": state,
            "labels": labels,
            "milestones": milestones,
            "query": query,
            "limit": limit,
        }
        return FakeGiteaResponse([{"number": 3, "title": "Sprint task"}])


def test_gitea_config_redacts_token_and_sensitive_url_query() -> None:
    env = {
        "GITEA_BASE_URL": "https://user:password@gitea.example.local?token=secret-value",
        "GITEA_TOKEN": "private-gitea-token",
        "GITEA_OWNER": "team",
        "GITEA_REPO": "workboard",
    }

    with patch.dict("os.environ", env, clear=True):
        result = server.gitea_workboard_config()

    assert result["config"]["token"] == "<set>"
    assert result["config"]["base_url"] == "https://<redacted>@gitea.example.local?token=%3Credacted%3E"
    assert "private-gitea-token" not in str(result)
    assert result["missing_for_repo_call"] == []
    assert result["write_enabled"] is False


def test_gitea_config_reads_write_gate_from_private_dotenv(tmp_path) -> None:
    dotenv = tmp_path / ".env"
    dotenv.write_text(
        "\n".join(
            [
                "GITEA_BASE_URL=https://gitea.example.local",
                "GITEA_OWNER=team",
                "GITEA_REPO=workboard",
                "GITEA_MCP_ALLOW_WRITE=1",
            ]
        ),
        encoding="utf-8",
    )

    with patch.dict("os.environ", {}, clear=True):
        result = server.gitea_workboard_config(dotenv_path=str(dotenv))

    assert result["write_enabled"] is True
    assert result["missing_for_repo_call"] == ["GITEA_TOKEN"]


def test_gitea_create_work_item_dry_run_does_not_require_token_or_network() -> None:
    env = {
        "GITEA_BASE_URL": "https://gitea.example.local",
        "GITEA_OWNER": "team",
        "GITEA_REPO": "workboard",
    }

    with patch.dict("os.environ", env, clear=True):
        result = server.gitea_create_work_item(
            title="Test work item",
            body="Private task body",
            labels=["type:feature"],
        )

    assert result["dry_run"] is True
    assert result["write_enabled"] is False
    assert result["payload"]["label_names"] == ["type:feature"]
    assert "GITEA_TOKEN" in result["required_execution_gates"]
    assert "GITEA_MCP_ALLOW_WRITE=1" in result["required_execution_gates"]


def test_gitea_create_work_item_execution_requires_gitea_write_gate() -> None:
    env = {
        "GITEA_BASE_URL": "https://gitea.example.local",
        "GITEA_TOKEN": "private-gitea-token",
        "GITEA_OWNER": "team",
        "GITEA_REPO": "workboard",
    }

    with patch.dict("os.environ", env, clear=True), pytest.raises(GiteaConfigError, match="GITEA_MCP_ALLOW_WRITE"):
        server.gitea_create_work_item(
            title="Test work item",
            body="Private task body",
            dry_run=False,
        )


def test_gitea_create_work_item_execution_resolves_labels_and_milestone_without_real_network() -> None:
    env = {
        "GITEA_BASE_URL": "https://gitea.example.local",
        "GITEA_TOKEN": "private-gitea-token",
        "GITEA_OWNER": "team",
        "GITEA_REPO": "workboard",
        "GITEA_DEFAULT_MILESTONE": "2026-07-S1",
        "GITEA_MCP_ALLOW_WRITE": "1",
    }
    FakeGiteaClient.created_issue_payload = None

    with patch.dict("os.environ", env, clear=True), patch.object(server, "GiteaClient", FakeGiteaClient):
        result = server.gitea_create_work_item(
            title="Test work item",
            body="Private task body",
            labels=["type:feature", "stage:build"],
            assignees=["lead"],
            dry_run=False,
        )

    assert result["dry_run"] is False
    assert result["write_enabled"] is True
    assert result["payload"]["resolved_label_ids"] == [11, 12]
    assert result["payload"]["resolved_milestone_id"] == 21
    assert result["response"]["body"]["number"] == 5
    assert FakeGiteaClient.created_issue_payload == {
        "title": "Test work item",
        "body": "Private task body",
        "labels": [11, 12],
        "assignees": ["lead"],
        "milestone": 21,
    }


def test_gitea_create_sprint_execution_uses_default_milestone_without_real_network() -> None:
    env = {
        "GITEA_BASE_URL": "https://gitea.example.local",
        "GITEA_TOKEN": "private-gitea-token",
        "GITEA_OWNER": "team",
        "GITEA_REPO": "workboard",
        "GITEA_DEFAULT_MILESTONE": "2026-07-S1",
        "GITEA_MCP_ALLOW_WRITE": "1",
    }
    FakeSprintClient.ensured = None

    with patch.dict("os.environ", env, clear=True), patch.object(server, "GiteaClient", FakeSprintClient):
        result = server.gitea_create_sprint(
            description="Sprint description",
            dry_run=False,
        )

    assert result["dry_run"] is False
    assert result["response"]["created"] is True
    assert FakeSprintClient.ensured == {
        "title": "2026-07-S1",
        "description": "Sprint description",
        "due_on": None,
        "state": "open",
    }


def test_gitea_list_sprint_tasks_filters_by_milestone_without_real_network() -> None:
    env = {
        "GITEA_BASE_URL": "https://gitea.example.local",
        "GITEA_TOKEN": "private-gitea-token",
        "GITEA_OWNER": "team",
        "GITEA_REPO": "workboard",
        "GITEA_DEFAULT_MILESTONE": "2026-07-S1",
    }
    FakeSprintClient.listed = None

    with patch.dict("os.environ", env, clear=True), patch.object(server, "GiteaClient", FakeSprintClient):
        result = server.gitea_list_sprint_tasks(labels=["type:feature"], state="all")

    assert result["response"]["body"][0]["number"] == 3
    assert FakeSprintClient.listed == {
        "state": "all",
        "labels": ["type:feature"],
        "milestones": ["2026-07-S1"],
        "query": None,
        "limit": 50,
    }


def test_gitea_standard_labels_template_parses_without_pyyaml_dependency() -> None:
    labels = load_standard_labels()

    assert len(labels) >= 20
    assert labels[1]["name"] == "type:feature"
    assert labels[1]["color"] == "#1D76DB"
    assert all(label["color"].startswith("#") for label in labels)
