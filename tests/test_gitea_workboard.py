from __future__ import annotations

from unittest.mock import patch

import pytest

from alterios_mcp import server
from alterios_mcp.delivery_evidence import parse_handoff_comment
from alterios_mcp.gitea_workboard import GiteaConfigError, agent_report_body, load_standard_labels
from alterios_mcp.gitea_workboard import (
    GiteaConfig,
    build_board_sync_plan,
    cookie_header_from_file,
    parse_project_board_html,
    sync_board_by_labels,
    transition_issue_stage,
)


class FakeGiteaResponse:
    def __init__(self, body: object, status_code: int = 200) -> None:
        self.status_code = status_code
        self.body = body

    def as_dict(self) -> dict[str, object]:
        return {"status_code": self.status_code, "content_type": "application/json", "body": self.body}


def test_agent_report_body_matches_delivery_evidence_contract() -> None:
    body = agent_report_body(
        role="implementer",
        scope="Implement tool profiles",
        inputs="Issue and repository",
        findings="Profiles implemented",
        artifacts="source and tests",
        verification="pytest passed",
        risks="none",
        next_step="hand off to verifier",
    )

    assert set(parse_handoff_comment(body)) == {
        "role",
        "scope",
        "inputs",
        "findings",
        "artifacts",
        "verification",
        "risks",
        "next",
    }


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


class FakeBoardSyncClient:
    def __init__(self, issues: list[dict[str, object]], columns: list[dict[str, object]]) -> None:
        self.issues = issues
        self.columns = columns
        self.moved: list[dict[str, object]] = []

    def list_issues(
        self,
        *,
        state: str = "open",
        labels: list[str] | None = None,
        milestones: list[str] | None = None,
        query: str | None = None,
        limit: int = 20,
    ) -> FakeGiteaResponse:
        return FakeGiteaResponse(self.issues[:limit])

    def list_project_columns(self, project_id: int | str) -> FakeGiteaResponse:
        assert str(project_id) == "3"
        return FakeGiteaResponse(self.columns)

    def add_issue_to_project_column(self, column_id: int | str, issue_id: int) -> FakeGiteaResponse:
        self.moved.append({"column_id": str(column_id), "issue_id": issue_id})
        return FakeGiteaResponse({"column_id": str(column_id), "issue_id": issue_id})


class FailingWebBoardClient:
    def read_project_board(self, project_id: int | str) -> dict[str, object]:
        raise AssertionError(f"web board should not be used for project {project_id}")


class FakeStageTransitionClient:
    def __init__(self, labels: list[str]) -> None:
        self.labels = labels
        self.replaced_with: list[str | int] | None = None
        self.comments: list[str] = []

    def list_issue_labels(self, issue_number: int) -> FakeGiteaResponse:
        assert issue_number == 1
        return FakeGiteaResponse([{"name": label, "id": index + 1} for index, label in enumerate(self.labels)])

    def resolve_label_ids(self, label_names: list[str]) -> list[int]:
        assert label_names == ["stage:verify"]
        return [101]

    def replace_issue_labels(self, issue_number: int, labels: list[str | int]) -> FakeGiteaResponse:
        assert issue_number == 1
        self.replaced_with = labels
        self.labels = [str(label) for label in labels]
        return FakeGiteaResponse([{"name": label} for label in self.labels])

    def create_issue_comment(self, issue_number: int, body: str) -> FakeGiteaResponse:
        assert issue_number == 1
        self.comments.append(body)
        return FakeGiteaResponse({"id": 9, "body": body}, status_code=201)


def _board_config() -> GiteaConfig:
    return GiteaConfig(
        base_url="https://gitea.example.local",
        token="test-token",
        owner="team",
        repo="workboard",
        default_project="3",
    )


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


def test_gitea_board_sync_plan_maps_stage_labels_to_columns() -> None:
    issues = [
        {"id": 46, "number": 1, "title": "Done task", "labels": [{"name": "stage:done"}]},
        {"id": 47, "number": 2, "title": "Build task", "labels": [{"name": "stage:build"}]},
        {"id": 48, "number": 3, "title": "No stage", "labels": []},
        {"id": 49, "number": 4, "title": "Conflict", "labels": [{"name": "stage:done"}, {"name": "stage:build"}]},
    ]
    columns = [
        {"id": "10", "title": "In Progress"},
        {"id": "20", "title": "Done"},
    ]

    plan = build_board_sync_plan(
        issues=issues,
        columns=columns,
        stage_column_map={"stage:build": "In Progress", "stage:done": "Done"},
        current_cards={47: {"issue_id": 47, "column_id": "10", "column_title": "In Progress"}},
    )

    assert plan["move_count"] == 1
    assert plan["moves"][0]["issue_id"] == 46
    assert plan["moves"][0]["target_column_id"] == "20"
    assert plan["skipped_count"] == 1
    assert plan["missing_stage_count"] == 1
    assert plan["conflict_count"] == 1


def test_gitea_sync_board_by_labels_dry_run_reads_api_columns_without_real_network() -> None:
    client = FakeBoardSyncClient(
        issues=[
            {"id": 46, "number": 1, "title": "Done task", "labels": [{"name": "stage:done"}]},
            {"id": 47, "number": 2, "title": "Build task", "labels": [{"name": "stage:build"}]},
        ],
        columns=[
            {"id": "10", "title": "In Progress", "issues": [{"id": 47}]},
            {"id": "20", "title": "Done", "issues": []},
        ],
    )

    result = sync_board_by_labels(
        config=_board_config(),
        dry_run=True,
        dotenv_path=None,
        client=client,  # type: ignore[arg-type]
        web_client=FailingWebBoardClient(),  # type: ignore[arg-type]
    )

    assert result["dry_run"] is True
    assert result["payload"]["board_source"] == "api"
    assert result["payload"]["plan"]["move_count"] == 1
    assert result["payload"]["plan"]["moves"][0]["target_column"] == "Done"


def test_gitea_sync_board_by_labels_apply_requires_write_gate() -> None:
    client = FakeBoardSyncClient(
        issues=[{"id": 46, "number": 1, "title": "Done task", "labels": [{"name": "stage:done"}]}],
        columns=[{"id": "20", "title": "Done", "issues": []}],
    )

    with patch.dict("os.environ", {}, clear=True), pytest.raises(GiteaConfigError, match="GITEA_MCP_ALLOW_WRITE"):
        sync_board_by_labels(
            config=_board_config(),
            dry_run=False,
            dotenv_path=None,
            client=client,  # type: ignore[arg-type]
            web_client=FailingWebBoardClient(),  # type: ignore[arg-type]
        )


def test_gitea_sync_board_by_labels_apply_moves_cards_through_api() -> None:
    client = FakeBoardSyncClient(
        issues=[{"id": 46, "number": 1, "title": "Done task", "labels": [{"name": "stage:done"}]}],
        columns=[{"id": "20", "title": "Done", "issues": []}],
    )

    with patch.dict("os.environ", {"GITEA_MCP_ALLOW_WRITE": "1"}, clear=True):
        result = sync_board_by_labels(
            config=_board_config(),
            dry_run=False,
            dotenv_path=None,
            client=client,  # type: ignore[arg-type]
            web_client=FailingWebBoardClient(),  # type: ignore[arg-type]
        )

    assert result["dry_run"] is False
    assert result["response"]["apply_mode_used"] == "api"
    assert client.moved == [{"column_id": "20", "issue_id": 46}]


def test_gitea_board_html_and_cookie_parsers(tmp_path) -> None:
    html = """
    <script>window.config = {csrfToken: "csrf-123"};</script>
    <div class="project-column" data-id="20">
      <div class="project-column-title-text">Done</div>
      <div class="issue-card" data-issue="46"></div>
    </div>
    """
    board = parse_project_board_html(html)
    cookie_file = tmp_path / "cookies.txt"
    cookie_file.write_text(
        "# Netscape HTTP Cookie File\n"
        "gitea.example.local\tFALSE\t/\tTRUE\t0\ttest_cookie\tabc\n",
        encoding="utf-8",
    )

    assert board["csrf_token"] == "csrf-123"
    assert board["columns"][0]["title"] == "Done"
    assert board["current_cards"][46]["column_id"] == "20"
    assert cookie_header_from_file(cookie_file) == "test_cookie=abc"


def test_gitea_transition_issue_stage_dry_run_preserves_non_stage_labels() -> None:
    client = FakeStageTransitionClient(["type:chore", "area:mcp", "stage:done"])

    result = transition_issue_stage(
        config=_board_config(),
        issue_number=1,
        target_stage="verify",
        dry_run=True,
        dotenv_path=None,
        client=client,  # type: ignore[arg-type]
    )

    assert result["dry_run"] is True
    assert result["payload"]["current_stage_labels"] == ["stage:done"]
    assert result["payload"]["next_labels"] == ["type:chore", "area:mcp", "stage:verify"]
    assert client.replaced_with is None


def test_gitea_transition_issue_stage_apply_replaces_only_stage_label() -> None:
    client = FakeStageTransitionClient(["type:chore", "area:mcp", "stage:done"])

    with patch.dict("os.environ", {"GITEA_MCP_ALLOW_WRITE": "1"}, clear=True):
        result = transition_issue_stage(
            config=_board_config(),
            issue_number=1,
            target_stage="stage:verify",
            comment="Moved to verify",
            dry_run=False,
            dotenv_path=None,
            client=client,  # type: ignore[arg-type]
        )

    assert result["dry_run"] is False
    assert client.replaced_with == ["type:chore", "area:mcp", "stage:verify"]
    assert client.comments == ["Moved to verify"]
    assert result["response"]["readback"]["stage_labels"] == ["stage:verify"]
    assert result["response"]["readback"]["target_stage_set"] is True


def test_gitea_transition_issue_stage_apply_requires_write_gate() -> None:
    client = FakeStageTransitionClient(["type:chore", "stage:done"])

    with patch.dict("os.environ", {}, clear=True), pytest.raises(GiteaConfigError, match="GITEA_MCP_ALLOW_WRITE"):
        transition_issue_stage(
            config=_board_config(),
            issue_number=1,
            target_stage="verify",
            dry_run=False,
            dotenv_path=None,
            client=client,  # type: ignore[arg-type]
        )


def test_gitea_transition_issue_stage_rejects_unknown_stage() -> None:
    client = FakeStageTransitionClient(["type:chore", "stage:done"])

    with pytest.raises(ValueError, match="known stage"):
        transition_issue_stage(
            config=_board_config(),
            issue_number=1,
            target_stage="stage:qa",
            dry_run=True,
            dotenv_path=None,
            client=client,  # type: ignore[arg-type]
        )
