from __future__ import annotations

import json
import os
from dataclasses import dataclass
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


@dataclass(frozen=True)
class GiteaConfig:
    base_url: str = ""
    token: str = ""
    owner: str = ""
    repo: str = ""
    default_project: str = ""
    default_milestone: str = ""
    timeout_seconds: float = 20.0

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
