from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from html import unescape
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from .client import load_config_values, redact_sensitive, redact_url_value


class GiteaConfigError(RuntimeError):
    pass


class GiteaRequestError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None, body: Any = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.body = body


DEFAULT_STAGE_COLUMN_MAP: dict[str, str] = {
    "stage:intake": "Backlog",
    "stage:backlog": "Backlog",
    "stage:ready": "Ready",
    "stage:discovery": "Ready",
    "stage:design": "In Progress",
    "stage:build": "In Progress",
    "stage:in-progress": "In Progress",
    "stage:review": "Review",
    "stage:verify": "Verify",
    "stage:done": "Done",
    "stage:blocked": "Blocked",
}


@dataclass(frozen=True)
class GiteaConfig:
    base_url: str = ""
    token: str = ""
    owner: str = ""
    repo: str = ""
    default_project: str = ""
    default_milestone: str = ""
    timeout_seconds: float = 20.0
    board_cookie_header: str = ""
    board_cookie_file: str = ""
    board_csrf_token: str = ""

    @classmethod
    def from_env(cls, dotenv_path: str | Path | None = ".env") -> "GiteaConfig":
        effective_dotenv_path = dotenv_path
        if dotenv_path == ".env":
            effective_dotenv_path = (
                os.environ.get("GITEA_DOTENV_PATH")
                or os.environ.get("ALTERIOS_DOTENV_PATH")
                or ".env"
            )
        values = load_config_values(effective_dotenv_path)
        timeout_raw = values.get("GITEA_TIMEOUT_SECONDS", "20")
        try:
            timeout_seconds = float(timeout_raw)
        except ValueError as exc:
            raise GiteaConfigError("GITEA_TIMEOUT_SECONDS must be a number") from exc
        return cls(
            base_url=values.get("GITEA_BASE_URL", "").strip().rstrip("/"),
            token=values.get("GITEA_TOKEN", "").strip(),
            owner=values.get("GITEA_OWNER", "").strip(),
            repo=values.get("GITEA_REPO", "").strip(),
            default_project=values.get("GITEA_DEFAULT_PROJECT", "").strip(),
            default_milestone=values.get("GITEA_DEFAULT_MILESTONE", "").strip(),
            timeout_seconds=timeout_seconds,
            board_cookie_header=values.get("GITEA_BOARD_COOKIE_HEADER", "").strip(),
            board_cookie_file=values.get("GITEA_BOARD_COOKIE_FILE", "").strip(),
            board_csrf_token=values.get("GITEA_BOARD_CSRF_TOKEN", "").strip(),
        )

    def redacted(self) -> dict[str, Any]:
        return {
            "base_url": redact_url_value(self.base_url),
            "token": "<set>" if self.token else "<missing>",
            "owner": self.owner,
            "repo": self.repo,
            "default_project": self.default_project,
            "default_milestone": self.default_milestone,
            "timeout_seconds": self.timeout_seconds,
            "board_cookie_header": "<set>" if self.board_cookie_header else "<missing>",
            "board_cookie_file": "<set>" if self.board_cookie_file else "<missing>",
            "board_csrf_token": "<set>" if self.board_csrf_token else "<missing>",
        }

    def missing_for_base_call(self) -> list[str]:
        return [] if self.base_url else ["GITEA_BASE_URL"]

    def missing_for_repo_call(self) -> list[str]:
        missing = self.missing_for_base_call()
        if not self.token:
            missing.append("GITEA_TOKEN")
        if not self.owner:
            missing.append("GITEA_OWNER")
        if not self.repo:
            missing.append("GITEA_REPO")
        return missing

    def target(self) -> dict[str, str]:
        return {"owner": self.owner, "repo": self.repo}


@dataclass(frozen=True)
class GiteaResponse:
    status_code: int
    content_type: str
    body: Any

    def as_dict(self) -> dict[str, Any]:
        return {
            "status_code": self.status_code,
            "content_type": self.content_type,
            "body": redact_sensitive(self.body),
        }


class GiteaClient:
    def __init__(self, config: GiteaConfig):
        self.config = config

    def api_version(self) -> GiteaResponse:
        return self._request("GET", "/api/v1/version", allow_http_error=True, require_token=False)

    def repository(self) -> GiteaResponse:
        self._require_repo_config()
        return self._request("GET", f"/api/v1/repos/{_path(self.config.owner)}/{_path(self.config.repo)}")

    def list_issues(
        self,
        *,
        state: str = "open",
        labels: list[str] | None = None,
        milestones: list[str] | None = None,
        query: str | None = None,
        limit: int = 20,
    ) -> GiteaResponse:
        self._require_repo_config()
        params: dict[str, Any] = {"state": state, "type": "issues", "limit": limit}
        if labels:
            params["labels"] = ",".join(labels)
        if milestones:
            params["milestones"] = ",".join(milestones)
        if query:
            params["q"] = query
        return self._request("GET", f"/api/v1/repos/{_path(self.config.owner)}/{_path(self.config.repo)}/issues", params=params)

    def list_labels(self, *, limit: int = 200) -> GiteaResponse:
        self._require_repo_config()
        return self._request(
            "GET",
            f"/api/v1/repos/{_path(self.config.owner)}/{_path(self.config.repo)}/labels",
            params={"limit": limit},
        )

    def create_label(self, label: dict[str, Any]) -> GiteaResponse:
        self._require_repo_config()
        return self._request(
            "POST",
            f"/api/v1/repos/{_path(self.config.owner)}/{_path(self.config.repo)}/labels",
            body=_create_label_payload(label),
        )

    def list_milestones(self, *, state: str = "open", limit: int = 200) -> GiteaResponse:
        self._require_repo_config()
        return self._request(
            "GET",
            f"/api/v1/repos/{_path(self.config.owner)}/{_path(self.config.repo)}/milestones",
            params={"state": state, "limit": limit},
        )

    def create_milestone(self, payload: dict[str, Any]) -> GiteaResponse:
        self._require_repo_config()
        return self._request(
            "POST",
            f"/api/v1/repos/{_path(self.config.owner)}/{_path(self.config.repo)}/milestones",
            body=payload,
        )

    def ensure_milestone(
        self,
        *,
        title: str,
        description: str = "",
        due_on: str | None = None,
        state: str = "open",
    ) -> dict[str, Any]:
        normalized_title = title.strip()
        if not normalized_title:
            raise ValueError("milestone title must not be empty.")
        response = self.list_milestones(state="all")
        milestones = response.body if isinstance(response.body, list) else []
        for item in milestones:
            if isinstance(item, dict) and item.get("title") == normalized_title:
                return {"created": False, "milestone": item}
        payload: dict[str, Any] = {"title": normalized_title, "state": state}
        if description:
            payload["description"] = description
        if due_on:
            payload["due_on"] = due_on
        created = self.create_milestone(payload)
        return {"created": True, "milestone": created.body, "response": created.as_dict()}

    def create_issue(self, payload: dict[str, Any]) -> GiteaResponse:
        self._require_repo_config()
        return self._request(
            "POST",
            f"/api/v1/repos/{_path(self.config.owner)}/{_path(self.config.repo)}/issues",
            body=payload,
        )

    def create_issue_comment(self, issue_number: int, body: str) -> GiteaResponse:
        self._require_repo_config()
        return self._request(
            "POST",
            f"/api/v1/repos/{_path(self.config.owner)}/{_path(self.config.repo)}/issues/{issue_number}/comments",
            body={"body": body},
        )

    def list_repo_projects(self, *, state: str = "open", limit: int = 100) -> GiteaResponse:
        self._require_repo_config()
        return self._request(
            "GET",
            f"/api/v1/repos/{_path(self.config.owner)}/{_path(self.config.repo)}/projects",
            params={"state": state, "limit": limit},
        )

    def list_project_columns(self, project_id: int | str) -> GiteaResponse:
        self._require_repo_config()
        return self._request(
            "GET",
            f"/api/v1/repos/{_path(self.config.owner)}/{_path(self.config.repo)}/projects/{project_id}/columns",
        )

    def add_issue_to_project_column(self, column_id: int | str, issue_id: int) -> GiteaResponse:
        self._require_repo_config()
        return self._request(
            "POST",
            f"/api/v1/repos/{_path(self.config.owner)}/{_path(self.config.repo)}/projects/columns/{column_id}/issues",
            body={"issue_id": issue_id},
        )

    def resolve_label_ids(self, label_names: list[str]) -> list[int]:
        if not label_names:
            return []
        response = self.list_labels()
        labels = response.body if isinstance(response.body, list) else []
        by_name = {str(label.get("name")): label for label in labels if isinstance(label, dict)}
        missing = [name for name in label_names if name not in by_name]
        if missing:
            raise GiteaConfigError("Missing Gitea labels: " + ", ".join(missing))
        return [int(by_name[name]["id"]) for name in label_names]

    def resolve_milestone_id(self, milestone: str | int | None) -> int | None:
        if milestone is None or milestone == "":
            return None
        if isinstance(milestone, int):
            return milestone
        normalized = milestone.strip()
        if not normalized:
            return None
        if normalized.isdigit():
            return int(normalized)
        response = self.list_milestones(state="all")
        milestones = response.body if isinstance(response.body, list) else []
        for item in milestones:
            if not isinstance(item, dict):
                continue
            if item.get("title") == normalized or item.get("name") == normalized:
                return int(item["id"])
        raise GiteaConfigError(f"Missing Gitea milestone: {normalized}")

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
        allow_http_error: bool = False,
        require_token: bool = True,
    ) -> GiteaResponse:
        if not self.config.base_url:
            raise GiteaConfigError("Missing required configuration: GITEA_BASE_URL")
        if require_token and not self.config.token:
            raise GiteaConfigError("Missing required configuration: GITEA_TOKEN")
        url = self.config.base_url + path
        if params:
            query = urlencode({key: value for key, value in params.items() if value not in (None, "", [])})
            if query:
                url += "?" + query
        data = None
        headers = {"Accept": "application/json"}
        if self.config.token:
            headers["Authorization"] = f"token {self.config.token}"
        if body is not None:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = Request(url, data=data, headers=headers, method=method.upper())
        try:
            with urlopen(request, timeout=self.config.timeout_seconds) as response:
                return GiteaResponse(
                    status_code=response.status,
                    content_type=response.headers.get("Content-Type", ""),
                    body=_decode_body(response.read(), response.headers.get("Content-Type", "")),
                )
        except HTTPError as exc:
            decoded = _decode_body(exc.read(), exc.headers.get("Content-Type", ""))
            if allow_http_error:
                return GiteaResponse(
                    status_code=exc.code,
                    content_type=exc.headers.get("Content-Type", ""),
                    body=decoded,
                )
            raise GiteaRequestError(
                f"Gitea HTTP {exc.code}: {_safe_error(decoded)}",
                status_code=exc.code,
                body=decoded,
            ) from exc
        except URLError as exc:
            raise GiteaRequestError(f"Gitea request failed: {exc.reason}") from exc

    def _require_repo_config(self) -> None:
        missing = self.config.missing_for_repo_call()
        if missing:
            raise GiteaConfigError("Missing required configuration: " + ", ".join(missing))


def build_issue_payload(
    *,
    title: str,
    body: str,
    label_ids: list[int] | None = None,
    assignees: list[str] | None = None,
    milestone_id: int | None = None,
    due_date: str | None = None,
    ref: str | None = None,
) -> dict[str, Any]:
    if not title.strip():
        raise ValueError("title must not be empty.")
    payload: dict[str, Any] = {"title": title.strip(), "body": body}
    if label_ids:
        payload["labels"] = label_ids
    if assignees:
        payload["assignees"] = [item.strip() for item in assignees if item.strip()]
    if milestone_id is not None:
        payload["milestone"] = milestone_id
    if due_date:
        payload["due_date"] = due_date
    if ref:
        payload["ref"] = ref
    return payload


class GiteaBoardWebClient:
    def __init__(self, config: GiteaConfig):
        self.config = config

    def read_project_board(self, project_id: int | str) -> dict[str, Any]:
        html = self._request_text("GET", f"/{_path(self.config.owner)}/-/projects/{project_id}")
        board = parse_project_board_html(html)
        if not board["columns"]:
            raise GiteaConfigError(
                "Project board was not found in web response. Check GITEA_BOARD_COOKIE_HEADER or GITEA_BOARD_COOKIE_FILE."
            )
        return {
            "project_id": str(project_id),
            "csrf_token_found": bool(board.get("csrf_token")),
            "columns": board["columns"],
            "current_cards": board["current_cards"],
        }

    def move_issue_to_column(
        self,
        *,
        project_id: int | str,
        column_id: int | str,
        issue_id: int,
        existing_target_issue_ids: list[int] | None = None,
    ) -> GiteaResponse:
        issue_ids = [item for item in (existing_target_issue_ids or []) if item != issue_id]
        issue_ids.append(issue_id)
        payload = {
            "issues": [
                {"issueID": item, "sorting": index}
                for index, item in enumerate(issue_ids)
            ]
        }
        body = self._request_text(
            "POST",
            f"/{_path(self.config.owner)}/-/projects/{project_id}/{column_id}/move",
            json_body=payload,
            csrf_project_id=project_id,
        )
        return GiteaResponse(status_code=200, content_type="text/plain", body=body)

    def _request_text(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        csrf_project_id: int | str | None = None,
    ) -> str:
        if not self.config.base_url:
            raise GiteaConfigError("Missing required configuration: GITEA_BASE_URL")
        cookie_header = self._cookie_header()
        if not cookie_header:
            raise GiteaConfigError("Missing Gitea web session. Set GITEA_BOARD_COOKIE_HEADER or GITEA_BOARD_COOKIE_FILE.")

        data = None
        headers = {
            "Accept": "text/html,application/json,text/plain",
            "Cookie": cookie_header,
        }
        if json_body is not None:
            data = json.dumps(json_body, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
            headers["x-csrf-token"] = self._csrf_token(csrf_project_id)

        request = Request(self.config.base_url + path, data=data, headers=headers, method=method.upper())
        try:
            with urlopen(request, timeout=self.config.timeout_seconds) as response:
                return response.read().decode("utf-8", errors="replace")
        except HTTPError as exc:
            decoded = exc.read().decode("utf-8", errors="replace")
            raise GiteaRequestError(
                f"Gitea web HTTP {exc.code}: {decoded[:300]}",
                status_code=exc.code,
                body=decoded,
            ) from exc
        except URLError as exc:
            raise GiteaRequestError(f"Gitea web request failed: {exc.reason}") from exc

    def _cookie_header(self) -> str:
        if self.config.board_cookie_header:
            return self.config.board_cookie_header
        if not self.config.board_cookie_file:
            return ""
        return cookie_header_from_file(self.config.board_cookie_file)

    def _csrf_token(self, project_id: int | str | None = None) -> str:
        if self.config.board_csrf_token:
            return self.config.board_csrf_token
        effective_project_id = str(project_id or self.config.default_project).strip()
        if not effective_project_id:
            raise GiteaConfigError("GITEA_DEFAULT_PROJECT or explicit project_id is required to fetch csrfToken.")
        html = self._request_text("GET", f"/{_path(self.config.owner)}/-/projects/{effective_project_id}")
        token = parse_csrf_token(html)
        if not token:
            raise GiteaConfigError("Could not extract csrfToken from Gitea project page.")
        return token


def sync_board_by_labels(
    *,
    config: GiteaConfig,
    project_id: str | int | None = None,
    stage_column_map: dict[str, str] | None = None,
    state: str = "open",
    limit: int = 100,
    apply_mode: str = "auto",
    dry_run: bool = True,
    dotenv_path: str | Path | None = ".env",
    client: GiteaClient | None = None,
    web_client: GiteaBoardWebClient | None = None,
) -> dict[str, Any]:
    if state not in {"open", "closed", "all"}:
        raise ValueError("state must be one of: open, closed, all.")
    if limit < 1 or limit > 100:
        raise ValueError("limit must be between 1 and 100.")
    if apply_mode not in {"auto", "api", "web"}:
        raise ValueError("apply_mode must be one of: auto, api, web.")

    effective_project_id = str(project_id or config.default_project).strip()
    if not effective_project_id:
        raise ValueError("project_id must not be empty and GITEA_DEFAULT_PROJECT is not configured.")

    stage_map = normalize_stage_column_map(stage_column_map)
    api_client = client or GiteaClient(config)
    issues_response = api_client.list_issues(state=state, limit=limit)
    issues = issues_response.body if isinstance(issues_response.body, list) else []

    board_state = _load_board_state(
        api_client=api_client,
        web_client=web_client or GiteaBoardWebClient(config),
        project_id=effective_project_id,
        apply_mode=apply_mode,
    )
    plan = build_board_sync_plan(
        issues=issues,
        columns=board_state["columns"],
        stage_column_map=stage_map,
        current_cards=board_state.get("current_cards", {}),
    )
    response: dict[str, Any] = {
        "moved": [],
        "skipped_apply": dry_run,
        "apply_mode_used": None,
    }

    if not dry_run:
        assert_gitea_write_allowed(config, dry_run=False, dotenv_path=dotenv_path)
        response = _apply_board_sync_plan(
            config=config,
            plan=plan,
            board_state=board_state,
            project_id=effective_project_id,
            apply_mode=apply_mode,
            api_client=api_client,
            web_client=web_client or GiteaBoardWebClient(config),
        )

    return planned_gitea_result(
        operation="gitea_sync_board_by_labels",
        config=config,
        dry_run=dry_run,
        payload={
            "project_id": effective_project_id,
            "state": state,
            "limit": limit,
            "apply_mode": apply_mode,
            "stage_column_map": stage_map,
            "board_source": board_state["source"],
            "columns": [
                {"id": column.get("id"), "title": column.get("title")}
                for column in board_state["columns"]
            ],
            "board_errors": board_state.get("errors", []),
            "plan": plan,
        },
        response=response,
        dotenv_path=dotenv_path,
    )


def build_board_sync_plan(
    *,
    issues: list[Any],
    columns: list[dict[str, Any]],
    stage_column_map: dict[str, str],
    current_cards: dict[int, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    current_cards = current_cards or {}
    columns_by_title = {str(column.get("title")): column for column in columns}
    moves: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    missing_stage: list[dict[str, Any]] = []
    missing_column: list[dict[str, Any]] = []

    for issue in issues:
        if not isinstance(issue, dict):
            continue
        issue_ref = _issue_ref(issue)
        issue_id = _coerce_int(issue.get("id"))
        if issue_id is None:
            conflicts.append({**issue_ref, "reason": "missing_issue_id"})
            continue
        stage_labels = _issue_stage_labels(issue)
        if not stage_labels:
            missing_stage.append(issue_ref)
            continue
        mapped_labels = [label for label in stage_labels if label in stage_column_map]
        unknown_labels = [label for label in stage_labels if label not in stage_column_map]
        if len(mapped_labels) != 1 or unknown_labels:
            conflicts.append({**issue_ref, "stage_labels": stage_labels, "unknown_stage_labels": unknown_labels})
            continue
        stage_label = mapped_labels[0]
        target_column_title = stage_column_map[stage_label]
        target_column = columns_by_title.get(target_column_title)
        if not target_column:
            missing_column.append({**issue_ref, "stage_label": stage_label, "target_column": target_column_title})
            continue
        current = current_cards.get(issue_id)
        current_column_title = current.get("column_title") if current else None
        if current_column_title == target_column_title:
            skipped.append({**issue_ref, "stage_label": stage_label, "current_column": current_column_title})
            continue
        moves.append(
            {
                **issue_ref,
                "stage_label": stage_label,
                "current_column": current_column_title,
                "target_column": target_column_title,
                "target_column_id": target_column.get("id"),
            }
        )

    return {
        "move_count": len(moves),
        "moves": moves,
        "skipped_count": len(skipped),
        "skipped": skipped,
        "conflict_count": len(conflicts),
        "conflicts": conflicts,
        "missing_stage_count": len(missing_stage),
        "missing_stage": missing_stage,
        "missing_column_count": len(missing_column),
        "missing_column": missing_column,
    }


def _load_board_state(
    *,
    api_client: GiteaClient,
    web_client: GiteaBoardWebClient,
    project_id: str,
    apply_mode: str,
) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []

    if apply_mode in {"auto", "api"}:
        try:
            response = api_client.list_project_columns(project_id)
            columns, current_cards = _normalize_api_columns(response.body)
            if columns:
                return {
                    "source": "api",
                    "columns": columns,
                    "current_cards": current_cards,
                    "errors": errors,
                }
            errors.append({"source": "api", "message": "Project columns API returned no columns."})
        except (GiteaConfigError, GiteaRequestError) as exc:
            errors.append(_board_error("api", exc))
        if apply_mode == "api":
            return {"source": "unavailable", "columns": [], "current_cards": {}, "errors": errors}

    if apply_mode in {"auto", "web"}:
        try:
            board = web_client.read_project_board(project_id)
            return {
                "source": "web",
                "columns": board.get("columns", []),
                "current_cards": board.get("current_cards", {}),
                "errors": errors,
            }
        except (GiteaConfigError, GiteaRequestError, OSError) as exc:
            errors.append(_board_error("web", exc))

    return {"source": "unavailable", "columns": [], "current_cards": {}, "errors": errors}


def _apply_board_sync_plan(
    *,
    config: GiteaConfig,
    plan: dict[str, Any],
    board_state: dict[str, Any],
    project_id: str,
    apply_mode: str,
    api_client: GiteaClient,
    web_client: GiteaBoardWebClient,
) -> dict[str, Any]:
    if board_state.get("source") == "unavailable":
        raise GiteaConfigError("Project board state is unavailable; run dry-run and fix board_errors first.")
    if plan.get("conflict_count"):
        raise GiteaConfigError("Project board sync has stage label conflicts; fix labels before apply.")
    if plan.get("missing_column_count"):
        raise GiteaConfigError("Project board sync has missing target columns; create/map columns before apply.")

    source = str(board_state.get("source") or "")
    if apply_mode == "api" and source != "api":
        raise GiteaConfigError("apply_mode=api requires API board state.")
    if apply_mode == "web" and source != "web":
        raise GiteaConfigError("apply_mode=web requires web board state.")
    if source not in {"api", "web"}:
        raise GiteaConfigError(f"Unsupported board sync source: {source!r}.")

    moved = []
    if source == "api":
        for move in plan.get("moves", []):
            issue_id = _coerce_int(move.get("issue_id"))
            column_id = move.get("target_column_id")
            if issue_id is None or column_id in (None, ""):
                raise GiteaConfigError(f"Invalid move payload: {move!r}.")
            response = api_client.add_issue_to_project_column(column_id, issue_id).as_dict()
            moved.append({**move, "response": response})
        return {"moved": moved, "skipped_apply": False, "apply_mode_used": "api"}

    target_issue_ids = _target_issue_ids_by_column(board_state.get("columns", []))
    for move in plan.get("moves", []):
        issue_id = _coerce_int(move.get("issue_id"))
        column_id = str(move.get("target_column_id") or "")
        if issue_id is None or not column_id:
            raise GiteaConfigError(f"Invalid move payload: {move!r}.")
        response = web_client.move_issue_to_column(
            project_id=project_id,
            column_id=column_id,
            issue_id=issue_id,
            existing_target_issue_ids=target_issue_ids.get(column_id, []),
        ).as_dict()
        for issue_ids in target_issue_ids.values():
            while issue_id in issue_ids:
                issue_ids.remove(issue_id)
        target_issue_ids.setdefault(column_id, []).append(issue_id)
        moved.append({**move, "response": response})
    return {"moved": moved, "skipped_apply": False, "apply_mode_used": "web"}


def _normalize_api_columns(payload: Any) -> tuple[list[dict[str, Any]], dict[int, dict[str, Any]]]:
    columns_payload = payload if isinstance(payload, list) else []
    columns: list[dict[str, Any]] = []
    current_cards: dict[int, dict[str, Any]] = {}
    for column in columns_payload:
        if not isinstance(column, dict):
            continue
        column_id = column.get("id") or column.get("ID")
        title = str(column.get("title") or column.get("name") or "").strip()
        if column_id in (None, "") or not title:
            continue
        cards = []
        for raw_card in _api_column_cards(column):
            issue_id = _api_card_issue_id(raw_card)
            if issue_id is None:
                continue
            card = {
                "issue_id": issue_id,
                "column_id": str(column_id),
                "column_title": title,
            }
            current_cards[issue_id] = card
            cards.append(card)
        columns.append({"id": str(column_id), "title": title, "cards": cards})
    return columns, current_cards


def _api_column_cards(column: dict[str, Any]) -> list[Any]:
    for key in ("issues", "cards", "items"):
        value = column.get(key)
        if isinstance(value, list):
            return value
    return []


def _api_card_issue_id(card: Any) -> int | None:
    if not isinstance(card, dict):
        return _coerce_int(card)
    for key in ("issue_id", "issueID", "issueId"):
        issue_id = _coerce_int(card.get(key))
        if issue_id is not None:
            return issue_id
    nested = card.get("issue")
    if isinstance(nested, dict):
        return _coerce_int(nested.get("id"))
    return _coerce_int(card.get("id"))


def _target_issue_ids_by_column(columns: list[dict[str, Any]]) -> dict[str, list[int]]:
    result: dict[str, list[int]] = {}
    for column in columns:
        column_id = str(column.get("id") or "")
        if not column_id:
            continue
        result[column_id] = [
            issue_id
            for issue_id in (_coerce_int(card.get("issue_id")) for card in column.get("cards", []))
            if issue_id is not None
        ]
    return result


def _board_error(source: str, exc: BaseException) -> dict[str, Any]:
    status_code = getattr(exc, "status_code", None)
    result: dict[str, Any] = {"source": source, "message": str(exc)}
    if status_code is not None:
        result["status_code"] = status_code
    return result


def normalize_stage_column_map(stage_column_map: dict[str, str] | None = None) -> dict[str, str]:
    result = dict(DEFAULT_STAGE_COLUMN_MAP)
    for key, value in (stage_column_map or {}).items():
        normalized_key = str(key).strip()
        normalized_value = str(value).strip()
        if normalized_key and normalized_value:
            result[normalized_key] = normalized_value
    return result


def parse_project_board_html(html: str) -> dict[str, Any]:
    columns: list[dict[str, Any]] = []
    current_cards: dict[int, dict[str, Any]] = {}
    fragments = re.split(r'(?=<div[^>]*class="(?:[^"]*\s)?project-column(?:\s[^"]*)?")', html)
    for fragment in fragments[1:]:
        tag_match = re.match(r"<div(?P<attrs>[^>]*)>", fragment, re.DOTALL)
        if not tag_match:
            continue
        attrs = tag_match.group("attrs")
        body = fragment
        column_id = _html_attr(attrs, "data-id") or _html_attr(attrs, "data-column-id")
        title_match = re.search(
            r'<div[^>]*class="[^"]*\bproject-column-title-text\b[^"]*"[^>]*>(?P<title>.*?)</div>',
            body,
            re.DOTALL,
        )
        title = _clean_html(title_match.group("title")) if title_match else ""
        if not column_id or not title:
            continue
        cards = []
        for card_match in re.finditer(
            r'<div[^>]*class="[^"]*\bissue-card\b[^"]*"[^>]*(?:data-issue|data-issue-id)="(?P<issue>\d+)"',
            body,
            re.DOTALL,
        ):
            issue_id = int(card_match.group("issue"))
            card = {
                "issue_id": issue_id,
                "column_id": column_id,
                "column_title": title,
            }
            current_cards[issue_id] = card
            cards.append(card)
        columns.append({"id": column_id, "title": title, "cards": cards})
    return {
        "csrf_token": parse_csrf_token(html),
        "columns": columns,
        "current_cards": current_cards,
    }


def _issue_ref(issue: dict[str, Any]) -> dict[str, Any]:
    return {
        "issue_id": _coerce_int(issue.get("id")),
        "number": _coerce_int(issue.get("number")),
        "title": str(issue.get("title") or ""),
        "url": issue.get("html_url") or issue.get("url"),
    }


def _issue_stage_labels(issue: dict[str, Any]) -> list[str]:
    labels = issue.get("labels") or []
    result: list[str] = []
    if not isinstance(labels, list):
        return result
    for label in labels:
        if isinstance(label, dict):
            name = str(label.get("name") or "").strip()
        else:
            name = str(label).strip()
        if name.startswith("stage:"):
            result.append(name)
    return result


def _html_attr(attrs: str, name: str) -> str:
    pattern = rf'\b{re.escape(name)}=(?:"([^"]*)"|\'([^\']*)\'|([^\s>]+))'
    match = re.search(pattern, attrs)
    if not match:
        return ""
    return unescape(next(group for group in match.groups() if group is not None))


def _clean_html(value: str) -> str:
    text = re.sub(r"<[^>]+>", "", value)
    return unescape(text).strip()


def _coerce_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def parse_csrf_token(html: str) -> str:
    patterns = [
        r"csrfToken:\s*'([^']+)'",
        r'csrfToken:\s*"([^"]+)"',
        r'<meta name="_csrf" content="([^"]+)"',
        r'<meta name="csrf-token" content="([^"]+)"',
    ]
    for pattern in patterns:
        match = re.search(pattern, html)
        if match:
            return unescape(match.group(1))
    return ""


def cookie_header_from_file(path: str | Path) -> str:
    cookie_path = Path(path).expanduser()
    text = cookie_path.read_text(encoding="utf-8")
    raw = text.strip()
    if not raw:
        return ""
    if "\t" not in raw and "=" in raw and "\n" not in raw:
        return raw
    pairs: list[str] = []
    for line in raw.splitlines():
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) >= 7:
            pairs.append(f"{parts[5]}={parts[6]}")
    return "; ".join(pairs)


def load_standard_labels(path: str | Path = "templates/gitea/labels.yaml") -> list[dict[str, Any]]:
    label_path = Path(path)
    if not label_path.exists():
        raise FileNotFoundError(f"Gitea labels template was not found: {label_path}")
    labels: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for raw_line in label_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or line == "labels:":
            continue
        if line.startswith("- name:"):
            if current:
                labels.append(current)
            current = {"name": _yaml_scalar(line.split(":", 1)[1])}
            continue
        if current is None or ":" not in line:
            continue
        key, value = line.split(":", 1)
        current[key.strip()] = _yaml_scalar(value)
    if current:
        labels.append(current)
    return [_create_label_payload(label) for label in labels]


def agent_report_body(
    *,
    role: str,
    scope: str,
    findings: str,
    artifacts: str = "",
    verification: str = "",
    risks: str = "",
    next_step: str = "",
) -> str:
    return "\n".join(
        [
            f"Роль: {role}",
            f"Scope: {scope}",
            f"Что сделано: {findings}",
            f"Артефакты: {artifacts}",
            f"Проверка: {verification}",
            f"Риски: {risks}",
            f"Следующий шаг: {next_step}",
        ]
    ).strip()


def planned_gitea_result(
    *,
    operation: str,
    config: GiteaConfig,
    dry_run: bool,
    payload: dict[str, Any],
    response: dict[str, Any] | None = None,
    dotenv_path: str | Path | None = ".env",
) -> dict[str, Any]:
    required_execution_gates = ["dry_run=false", "GITEA_MCP_ALLOW_WRITE=1"]
    if config.missing_for_repo_call():
        required_execution_gates.extend(config.missing_for_repo_call())
    write_enabled = gitea_write_enabled(dotenv_path)
    return {
        "dry_run": dry_run,
        "write_enabled": write_enabled,
        "target": config.target(),
        "operation": operation,
        "payload": redact_sensitive(payload),
        "response": redact_sensitive(response),
        "required_execution_gates": required_execution_gates,
        "will_execute": bool(not dry_run and write_enabled),
    }


def assert_gitea_write_allowed(
    config: GiteaConfig,
    *,
    dry_run: bool,
    dotenv_path: str | Path | None = ".env",
) -> None:
    if dry_run:
        return
    if not gitea_write_enabled(dotenv_path):
        raise GiteaConfigError("Gitea writes are disabled. Set GITEA_MCP_ALLOW_WRITE=1 explicitly.")
    missing = config.missing_for_repo_call()
    if missing:
        raise GiteaConfigError("Missing required configuration: " + ", ".join(missing))


def gitea_write_enabled(dotenv_path: str | Path | None = ".env") -> bool:
    effective_dotenv_path = dotenv_path
    if dotenv_path == ".env":
        effective_dotenv_path = (
            os.environ.get("GITEA_DOTENV_PATH")
            or os.environ.get("ALTERIOS_DOTENV_PATH")
            or ".env"
        )
    return load_config_values(effective_dotenv_path).get("GITEA_MCP_ALLOW_WRITE") == "1"


def _create_label_payload(label: dict[str, Any]) -> dict[str, Any]:
    name = str(label.get("name") or "").strip()
    color = str(label.get("color") or "").strip()
    if not name:
        raise ValueError("Gitea label name must not be empty.")
    if not color:
        raise ValueError(f"Gitea label {name!r} color must not be empty.")
    if not color.startswith("#"):
        color = "#" + color
    payload = {"name": name, "color": color}
    description = str(label.get("description") or "").strip()
    if description:
        payload["description"] = description
    return payload


def _yaml_scalar(value: str) -> str:
    normalized = value.strip()
    if (
        len(normalized) >= 2
        and normalized[0] == normalized[-1]
        and normalized[0] in {"'", '"'}
    ):
        return normalized[1:-1]
    return normalized


def _decode_body(response_body: bytes, content_type: str) -> Any:
    text = response_body.decode("utf-8", errors="replace")
    if "json" in content_type.lower():
        return json.loads(text) if text.strip() else None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def _safe_error(payload: Any) -> str:
    redacted = redact_sensitive(payload)
    if isinstance(redacted, dict):
        return json.dumps(
            {key: redacted.get(key) for key in ("message", "errors", "url") if key in redacted},
            ensure_ascii=False,
        )
    return str(redacted)[:300]


def _path(value: str) -> str:
    return quote(value.strip(), safe="")
