from __future__ import annotations

import json
import mimetypes
import os
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen

from .services import get_service


class AlteriosConfigError(RuntimeError):
    pass


class AlteriosRequestError(RuntimeError):
    pass


PROFILE_CONFIG_SUFFIXES = (
    "BASE_URL",
    "API_TOKEN",
    "PROJECT_ID",
    "ENDPOINT_TEMPLATE",
    "BODY_STYLE",
    "AUTH_HEADER",
    "AUTH_SCHEME",
    "TIMEOUT_SECONDS",
)
PROFILE_KEY_RE = re.compile(
    r"^ALTERIOS_(?P<profile>[A-Z0-9_]+)_(?P<suffix>"
    + "|".join(re.escape(suffix) for suffix in PROFILE_CONFIG_SUFFIXES)
    + r")$"
)


@dataclass(frozen=True)
class AlteriosConfig:
    profile: str = ""
    base_url: str = ""
    api_token: str = ""
    project_id: str = ""
    endpoint_template: str = ""
    body_style: str = "rpc"
    auth_header: str = "Authorization"
    auth_scheme: str = "Bearer"
    timeout_seconds: float = 20.0

    @classmethod
    def from_env(cls, dotenv_path: str | Path | None = ".env", profile: str | None = None) -> "AlteriosConfig":
        values = load_config_values(dotenv_path)

        selected_profile = (values.get("ALTERIOS_PROFILE", "") if profile is None else profile).strip()
        effective_values = apply_profile_values(values, selected_profile)

        timeout_raw = effective_values.get("ALTERIOS_TIMEOUT_SECONDS", "20")
        try:
            timeout_seconds = float(timeout_raw)
        except ValueError as exc:
            raise AlteriosConfigError("ALTERIOS_TIMEOUT_SECONDS must be a number") from exc

        return cls(
            profile=selected_profile,
            base_url=effective_values.get("ALTERIOS_BASE_URL", "").strip(),
            api_token=effective_values.get("ALTERIOS_API_TOKEN", "").strip(),
            project_id=effective_values.get("ALTERIOS_PROJECT_ID", "").strip(),
            endpoint_template=effective_values.get("ALTERIOS_ENDPOINT_TEMPLATE", "").strip(),
            body_style=effective_values.get("ALTERIOS_BODY_STYLE", "rpc").strip() or "rpc",
            auth_header=effective_values.get("ALTERIOS_AUTH_HEADER", "Authorization").strip() or "Authorization",
            auth_scheme=effective_values.get("ALTERIOS_AUTH_SCHEME", "Bearer").strip(),
            timeout_seconds=timeout_seconds,
        )

    def missing_for_rest_call(self) -> list[str]:
        return self.missing_for_instance_call()

    def missing_for_instance_call(self) -> list[str]:
        missing: list[str] = []
        profile_key = normalize_profile_key(self.profile) if self.profile else ""
        api_token_key = f"ALTERIOS_{profile_key}_API_TOKEN" if profile_key else "ALTERIOS_API_TOKEN"
        base_url_key = f"ALTERIOS_{profile_key}_BASE_URL" if profile_key else "ALTERIOS_BASE_URL"
        if not self.api_token:
            missing.append(api_token_key)
        if not self.base_url:
            missing.append(base_url_key)
        return missing

    def missing_for_project_call(self) -> list[str]:
        missing = self.missing_for_instance_call()
        if not self.project_id:
            profile_key = normalize_profile_key(self.profile) if self.profile else ""
            project_id_key = f"ALTERIOS_{profile_key}_PROJECT_ID" if profile_key else "ALTERIOS_PROJECT_ID"
            missing.append(project_id_key)
        return missing

    def missing_for_script_call(self) -> list[str]:
        missing = self.missing_for_project_call()
        if not self.endpoint_template:
            missing.append(profile_env_key(self.profile, "ENDPOINT_TEMPLATE"))
        return missing

    def with_project_id(self, project_id: str | None) -> "AlteriosConfig":
        normalized = (project_id or "").strip()
        if not normalized:
            return self
        return AlteriosConfig(
            profile=self.profile,
            base_url=self.base_url,
            api_token=self.api_token,
            project_id=normalized,
            endpoint_template=self.endpoint_template,
            body_style=self.body_style,
            auth_header=self.auth_header,
            auth_scheme=self.auth_scheme,
            timeout_seconds=self.timeout_seconds,
        )

    def redacted(self) -> dict[str, Any]:
        return {
            "profile": self.profile or "<default>",
            "base_url": redact_url_value(self.base_url),
            "api_token": "<set>" if self.api_token else "<missing>",
            "project_id": self.project_id,
            "endpoint_template": redact_url_value(self.endpoint_template),
            "body_style": self.body_style,
            "auth_header": self.auth_header,
            "auth_scheme": self.auth_scheme,
            "timeout_seconds": self.timeout_seconds,
        }


@dataclass(frozen=True)
class PreparedAlteriosRequest:
    method: str
    url: str
    headers: dict[str, str]
    body: Any

    def redacted(self) -> dict[str, Any]:
        headers = dict(self.headers)
        for key in list(headers):
            if key.lower() in {"authorization", "x-api-key"}:
                headers[key] = "<redacted>"
        return {"method": self.method, "url": self.url, "headers": headers, "body": self.body}


@dataclass(frozen=True)
class AlteriosResponse:
    status_code: int
    content_type: str
    body: Any

    def as_dict(self) -> dict[str, Any]:
        return {"status_code": self.status_code, "content_type": self.content_type, "body": redact_sensitive(self.body)}


class AlteriosClient:
    def __init__(self, config: AlteriosConfig):
        self.config = config

    def prepare_script_request(
        self,
        function: str,
        args: Any = None,
        *,
        body_style: str | None = None,
        allow_write: bool = False,
    ) -> PreparedAlteriosRequest:
        service = get_service(function)
        if service.mutates and not allow_write:
            raise AlteriosRequestError(
                f"{function} changes Alterios state. Enable write mode only if this is intentional."
            )

        missing = self.config.missing_for_script_call()
        if missing:
            raise AlteriosConfigError(f"Missing required configuration: {', '.join(missing)}")

        url = self.build_script_url(function)
        if _looks_like_execute_manual_url(url) and not looks_like_uuid(function):
            raise AlteriosRequestError(
                "Configured endpoint is /api/scripts/execute-manual, which requires a script UUID. "
                "Runtime service names from the catalog are not directly executable through this endpoint."
            )

        body = build_script_body(function, args, body_style or self.config.body_style)
        return PreparedAlteriosRequest(
            method="POST",
            url=url,
            headers=self._headers(),
            body=body,
        )

    def call_script_service(
        self,
        function: str,
        args: Any = None,
        *,
        body_style: str | None = None,
        allow_write: bool = False,
    ) -> AlteriosResponse:
        prepared = self.prepare_script_request(
            function,
            args,
            body_style=body_style,
            allow_write=allow_write,
        )
        return self._send(prepared)

    def execute_manual_script(self, script_id: str, args: Any = None) -> AlteriosResponse:
        if not looks_like_uuid(script_id):
            raise AlteriosConfigError("manual script execution requires a script UUID")
        missing = self.config.missing_for_script_call()
        if missing:
            raise AlteriosConfigError(f"Missing required configuration: {', '.join(missing)}")
        prepared = PreparedAlteriosRequest(
            method="POST",
            url=self.build_script_url(script_id),
            headers=self._headers(),
            body=build_script_body(script_id, args, "manual_script"),
        )
        return self._send(prepared)

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        body: Any | None = None,
        requires_project: bool = True,
    ) -> AlteriosResponse:
        missing = self.config.missing_for_project_call() if requires_project else self.config.missing_for_instance_call()
        if missing:
            raise AlteriosConfigError(f"Missing required configuration: {', '.join(missing)}")

        path = "/" + path.lstrip("/")
        query = urlencode({key: value for key, value in (params or {}).items() if value is not None}, doseq=True)
        url = self.config.base_url.rstrip("/") + path + (f"?{query}" if query else "")
        prepared = PreparedAlteriosRequest(method=method.upper(), url=url, headers=self._headers(), body=body)
        return self._send(prepared)

    def report_full(self, report_id: str) -> AlteriosResponse:
        encoded_filter = encode_filter({"_id": report_id})
        return self.request("GET", f"/api/reports/full/{encoded_filter}")

    def view_full(self, view_id: str) -> AlteriosResponse:
        return self.request("GET", f"/api/views/{path_segment(view_id)}")

    def form_full(self, form_id: str) -> AlteriosResponse:
        return self.request("GET", f"/api/forms/{path_segment(form_id)}")

    def list_views(self, *, limit: int = 1000, offset: int = 0) -> AlteriosResponse:
        return self.request("GET", "/api/views/listandcount", params={"limit": limit, "offset": offset})

    def list_forms(self, *, limit: int = 1000, offset: int = 0) -> AlteriosResponse:
        return self.request("GET", "/api/forms/listandcount", params={"limit": limit, "offset": offset})

    def list_scripts(self, *, limit: int = 1000, offset: int = 0) -> AlteriosResponse:
        return self.request("GET", "/api/scripts/listandcount", params={"limit": limit, "offset": offset})

    def list_diagrams(self, *, limit: int = 1000, offset: int = 0) -> AlteriosResponse:
        return self.request("GET", "/api/diagrams/listandcount", params={"limit": limit, "offset": offset})

    def list_reports(self, *, limit: int = 1000, offset: int = 0) -> AlteriosResponse:
        return self.request("GET", f"/api/reports/listandcount/{encode_filter({})}", params={"limit": limit, "offset": offset})

    def list_content_types(self, *, limit: int = 1000, offset: int = 0) -> AlteriosResponse:
        return self.request("GET", "/api/content-types/listandcount", params={"limit": limit, "offset": offset})

    def list_shared_content_types(self) -> AlteriosResponse:
        return self.request("GET", "/api/content-types", params={"share": "true"})

    def list_users(self, *, limit: int = 1000, offset: int = 0) -> AlteriosResponse:
        return self.request("GET", "/api/users/listandcount", params={"limit": limit, "offset": offset})

    def list_user_groups(self, *, limit: int = 1000, offset: int = 0) -> AlteriosResponse:
        return self.request("GET", "/api/user-groups/listandcount", params={"limit": limit, "offset": offset})

    def list_roles(self, *, limit: int = 1000, offset: int = 0) -> AlteriosResponse:
        return self.request("GET", "/api/roles/listandcount", params={"limit": limit, "offset": offset})

    def view_by_id(self, view_id: str) -> AlteriosResponse:
        return self._listandcount_item_by_id("/api/views/listandcount", view_id, "View")

    def content_type_by_id(self, content_type_id: str) -> AlteriosResponse:
        return self._listandcount_item_by_id("/api/content-types/listandcount", content_type_id, "Content type")

    def user_by_id(self, user_id: str) -> AlteriosResponse:
        return self._listandcount_item_by_id("/api/users/listandcount", user_id, "User")

    def user_group_by_id(self, user_group_id: str) -> AlteriosResponse:
        return self._listandcount_item_by_id("/api/user-groups/listandcount", user_group_id, "User group")

    def role_by_id(self, role_id: str) -> AlteriosResponse:
        return self._listandcount_item_by_id("/api/roles/listandcount", role_id, "Role")

    def field_by_id(self, field_id: str) -> AlteriosResponse:
        response = self.list_fields(field_id=field_id, limit=1, offset=0)
        body = response.body
        items = [item for item in body if isinstance(item, dict)] if isinstance(body, list) else listandcount_items(body)
        if not items:
            raise AlteriosRequestError(f"Field {field_id!r} was not found.")
        return AlteriosResponse(response.status_code, response.content_type, items[0])

    def form_by_id(self, form_id: str) -> AlteriosResponse:
        return self._listandcount_item_by_id("/api/forms/listandcount", form_id, "Form")

    def script_by_id(self, script_id: str) -> AlteriosResponse:
        return self._listandcount_item_by_id("/api/scripts/listandcount", script_id, "Script")

    def diagram_by_id(self, diagram_id: str) -> AlteriosResponse:
        return self._listandcount_item_by_id("/api/diagrams/listandcount", diagram_id, "Diagram")

    def report_by_id(self, report_id: str) -> AlteriosResponse:
        response = self.report_full(report_id)
        item = report_full_item(response.body)
        if not isinstance(item, dict) or not item.get("_id"):
            raise AlteriosRequestError(f"Report {report_id!r} was not found.")
        return AlteriosResponse(response.status_code, response.content_type, item)

    def view_entities(self, view_id: str) -> AlteriosResponse:
        return self.request("GET", f"/api/view-entities/by-view/{path_segment(view_id)}")

    def view_fields_populated(self, view_id: str) -> AlteriosResponse:
        return self.request("GET", f"/api/view-fields/populated/{path_segment(view_id)}")

    def save_view(self, payload: dict[str, Any]) -> AlteriosResponse:
        return self.save_resource("views", payload)

    def save_form(self, payload: dict[str, Any]) -> AlteriosResponse:
        return self.save_resource("forms", payload)

    def save_view_entity(self, payload: dict[str, Any]) -> AlteriosResponse:
        return self.save_resource("view-entities", payload)

    def save_script(self, payload: dict[str, Any]) -> AlteriosResponse:
        body = strip_alterios_metadata(payload)
        if self.config.api_token:
            body["apiKey"] = self.config.api_token
        if body.get("_id"):
            return self.request("PUT", "/api/scripts", body=body)
        return self.request("POST", "/api/scripts", body=body)

    def save_diagram(self, payload: dict[str, Any]) -> AlteriosResponse:
        return self.save_resource("diagrams", payload)

    def save_report(self, payload: dict[str, Any]) -> AlteriosResponse:
        body = strip_alterios_metadata(payload)
        if body.get("_id"):
            return self.request("PUT", "/api/reports", body=body)
        return self.request("POST", "/api/reports", body=body)

    def save_content_type(self, payload: dict[str, Any]) -> AlteriosResponse:
        return self.request("POST", "/api/content-types/save", body=strip_alterios_metadata(payload))

    def clone_content_type(self, content_type_id: str) -> AlteriosResponse:
        if not content_type_id.strip():
            raise ValueError("content_type_id must not be empty")
        return self.request("POST", "/api/content-types/clone", body={"id": content_type_id})

    def save_field(self, payload: dict[str, Any]) -> AlteriosResponse:
        return self.request("POST", "/api/fields/save", body=strip_alterios_metadata(payload))

    def create_content(
        self,
        content_type_id: str,
        field_values: dict[str, Any],
        *,
        groups_ids: list[str] | None = None,
        name: str | None = None,
    ) -> AlteriosResponse:
        if not content_type_id.strip():
            raise ValueError("content_type_id must not be empty")
        if not field_values:
            raise ValueError("field_values must contain at least one field")
        payload: dict[str, Any] = {
            "contentTypeId": content_type_id,
            "fields": {str(key): normalize_content_field_value(value) for key, value in field_values.items()},
        }
        if groups_ids is not None:
            payload["groupsIds"] = groups_ids
        if name is not None:
            payload["name"] = name
        return self.request("POST", "/api/contents/save", body=payload)

    def save_group(self, payload: dict[str, Any]) -> AlteriosResponse:
        return self.save_resource("groups", payload)

    def save_user(self, payload: dict[str, Any]) -> AlteriosResponse:
        return self.save_resource("users", payload)

    def save_user_group(self, payload: dict[str, Any]) -> AlteriosResponse:
        return self.save_resource("user-groups", payload)

    def save_role(self, payload: dict[str, Any]) -> AlteriosResponse:
        return self.save_resource("roles", payload)

    def delete_user(self, user_id: str) -> AlteriosResponse:
        if not user_id.strip():
            raise ValueError("user_id must not be empty")
        return self.request("DELETE", "/api/users", body={"_id": user_id})

    def delete_user_group(self, user_group_id: str) -> AlteriosResponse:
        return self.delete_resource("user-groups", user_group_id)

    def delete_role(self, role_id: str) -> AlteriosResponse:
        return self.delete_resource("roles", role_id)

    def list_helps(self) -> AlteriosResponse:
        return self.request("GET", "/api/helps")

    def help_by_id(self, help_id: str) -> AlteriosResponse:
        response = self.list_helps()
        items = listandcount_items(response.body)
        for item in items:
            if item.get("_id") == help_id:
                return AlteriosResponse(response.status_code, response.content_type, item)
        raise AlteriosRequestError(f"Help {help_id!r} was not found.")

    def save_help(self, payload: dict[str, Any]) -> AlteriosResponse:
        return self.save_resource("helps", payload)

    def add_view_entity_field(
        self,
        entity_id: str,
        *,
        attribute: str | None = None,
        content_type_field_id: str | None = None,
        content_type_id: str | None = None,
    ) -> AlteriosResponse:
        if bool(attribute) == bool(content_type_field_id):
            raise ValueError("Pass exactly one of attribute or content_type_field_id.")
        body: dict[str, Any] = {"entityId": entity_id}
        if attribute:
            body["attribute"] = attribute
        if content_type_field_id:
            body["contentTypeFieldId"] = content_type_field_id
        return self.request("POST", "/api/view-entities/add-one-field", body=body)

    def save_view_field(self, payload: dict[str, Any]) -> AlteriosResponse:
        return self.request("POST", "/api/view-fields/save", body=strip_alterios_metadata(payload))

    def list_fields(
        self,
        *,
        content_type_id: str | None = None,
        field_id: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> AlteriosResponse:
        params: dict[str, Any] = {
            "contentTypeId": content_type_id,
            "_id": field_id,
            "limit": limit,
            "offset": offset,
        }
        return self.request("GET", "/api/fields", params=params)

    def list_groups(self) -> AlteriosResponse:
        return self.request("GET", "/api/groups")

    def file_metadata(self, file_ids: list[str]) -> AlteriosResponse:
        if not file_ids:
            raise ValueError("file_ids must contain at least one file id")
        return self.request("GET", "/api/file/list", params={"id": file_ids})

    def file_elfinder(self, *, command: str = "open", target: str | None = None, extra: dict[str, Any] | None = None) -> AlteriosResponse:
        command = command.strip()
        if not command:
            raise ValueError("elFinder command must not be empty")
        params: dict[str, Any] = {"cmd": command}
        if target:
            params["target"] = target
        if extra:
            params.update(extra)
        return self.request("GET", "/api/file/elfinder", params=params)

    def download_file(self, file_id: str) -> tuple[bytes, str]:
        if not file_id.strip():
            raise ValueError("file_id must not be empty")
        missing = self.config.missing_for_project_call()
        if missing:
            raise AlteriosConfigError(f"Missing required configuration: {', '.join(missing)}")
        request = Request(
            self.config.base_url.rstrip("/") + f"/api/file/download/{path_segment(file_id)}",
            headers=self._headers(),
            method="GET",
        )
        try:
            with urlopen(request, timeout=self.config.timeout_seconds) as response:
                return response.read(), response.headers.get("Content-Type", "")
        except HTTPError as exc:
            content_type = exc.headers.get("Content-Type", "") if exc.headers else ""
            parsed_body = parse_response_body(exc.read(), content_type)
            raise AlteriosRequestError(f"HTTP {exc.code}: {safe_error(parsed_body)}") from exc
        except TimeoutError as exc:
            raise AlteriosRequestError("Network error: timed out") from exc
        except URLError as exc:
            raise AlteriosRequestError(f"Network error: {exc.reason}") from exc

    def download_file_url(self, file_url: str) -> tuple[bytes, str]:
        if not file_url.strip():
            raise ValueError("file_url must not be empty")
        missing = self.config.missing_for_project_call()
        if missing:
            raise AlteriosConfigError(f"Missing required configuration: {', '.join(missing)}")
        parsed = urlsplit(file_url)
        if parsed.scheme and parsed.netloc:
            url = urlunsplit((parsed.scheme, parsed.netloc, quote(parsed.path, safe="/%"), parsed.query, parsed.fragment))
        else:
            relative = urlsplit("/" + file_url.lstrip("/"))
            url = self.config.base_url.rstrip("/") + urlunsplit(
                ("", "", quote(relative.path, safe="/%"), relative.query, relative.fragment)
            )
        headers = dict(self._headers())
        headers["Accept"] = "*/*"
        headers.pop("Content-Type", None)
        request = Request(url, headers=headers, method="GET")
        try:
            with urlopen(request, timeout=self.config.timeout_seconds) as response:
                return response.read(), response.headers.get("Content-Type", "")
        except HTTPError as exc:
            content_type = exc.headers.get("Content-Type", "") if exc.headers else ""
            parsed_body = parse_response_body(exc.read(), content_type)
            raise AlteriosRequestError(f"HTTP {exc.code}: {safe_error(parsed_body)}") from exc
        except TimeoutError as exc:
            raise AlteriosRequestError("Network error: timed out") from exc
        except URLError as exc:
            raise AlteriosRequestError(f"Network error: {exc.reason}") from exc

    def content_by_id(self, content_id: str) -> AlteriosResponse:
        if not content_id.strip():
            raise ValueError("content_id must not be empty")
        response = self.request(
            "GET",
            "/api/contents/listandcount",
            params={"_id": content_id, "limit": 1, "offset": 0},
        )
        items = listandcount_items(response.body)
        if not items:
            raise AlteriosRequestError(f"Content {content_id!r} was not found.")
        return AlteriosResponse(response.status_code, response.content_type, items[0])

    def update_content_fields(
        self,
        content_id: str,
        field_values: dict[str, Any],
        *,
        content_type_id: str | None = None,
        groups_ids: list[str] | None = None,
        name: str | None = None,
    ) -> AlteriosResponse:
        if not field_values:
            raise ValueError("field_values must contain at least one field")
        existing = self.content_by_id(content_id).body
        if not isinstance(existing, dict):
            raise AlteriosRequestError("Content readback returned unexpected payload.")
        payload = content_update_payload(
            existing,
            field_values,
            content_type_id=content_type_id,
            groups_ids=groups_ids,
            name=name,
        )
        return self.request("PATCH", "/api/contents/save", body=payload)

    def upload_file_to_field(
        self,
        data: bytes,
        *,
        filename: str,
        content_type_id: str,
        field_id: str,
        mime_type: str | None = None,
    ) -> AlteriosResponse:
        if not data:
            raise ValueError("file data must not be empty")
        if not filename.strip():
            raise ValueError("filename must not be empty")
        if not content_type_id.strip():
            raise ValueError("content_type_id must not be empty")
        if not field_id.strip():
            raise ValueError("field_id must not be empty")

        boundary = "----CodexAlteriosBoundary" + uuid.uuid4().hex
        resolved_mime_type = mime_type or mimetypes.guess_type(filename)[0] or "application/octet-stream"
        body = build_multipart(boundary, "upload", filename, resolved_mime_type, data)
        headers = dict(self._headers())
        headers.update(
            {
                "Accept": "application/json",
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "Content-Length": str(len(body)),
                "contenttype": content_type_id,
                "field": field_id,
                "ngsw-bypass": "true",
            }
        )
        request = Request(
            self.config.base_url.rstrip("/") + "/api/file/upload/field",
            data=body,
            headers=headers,
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.config.timeout_seconds) as response:
                return AlteriosResponse(
                    response.status,
                    response.headers.get("Content-Type", ""),
                    parse_response_body(response.read(), response.headers.get("Content-Type", "")),
                )
        except HTTPError as exc:
            content_type = exc.headers.get("Content-Type", "") if exc.headers else ""
            parsed_body = parse_response_body(exc.read(), content_type)
            raise AlteriosRequestError(f"HTTP {exc.code}: {safe_error(parsed_body)}") from exc
        except TimeoutError as exc:
            raise AlteriosRequestError("Network error: timed out") from exc
        except URLError as exc:
            raise AlteriosRequestError(f"Network error: {exc.reason}") from exc

    def upload_icon(self, data: bytes, *, filename: str, mime_type: str | None = None) -> AlteriosResponse:
        if not data:
            raise ValueError("icon data must not be empty")
        if not filename.strip():
            raise ValueError("filename must not be empty")

        boundary = "----CodexAlteriosBoundary" + uuid.uuid4().hex
        resolved_mime_type = mime_type or mimetypes.guess_type(filename)[0] or "image/svg+xml"
        body = build_multipart(boundary, "upload", filename, resolved_mime_type, data)
        headers = dict(self._headers())
        headers.update(
            {
                "Accept": "application/json",
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "Content-Length": str(len(body)),
                "ngsw-bypass": "true",
            }
        )
        request = Request(
            self.config.base_url.rstrip("/") + "/api/file/upload/icon",
            data=body,
            headers=headers,
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.config.timeout_seconds) as response:
                return AlteriosResponse(
                    response.status,
                    response.headers.get("Content-Type", ""),
                    parse_response_body(response.read(), response.headers.get("Content-Type", "")),
                )
        except HTTPError as exc:
            content_type = exc.headers.get("Content-Type", "") if exc.headers else ""
            parsed_body = parse_response_body(exc.read(), content_type)
            raise AlteriosRequestError(f"HTTP {exc.code}: {safe_error(parsed_body)}") from exc
        except TimeoutError as exc:
            raise AlteriosRequestError("Network error: timed out") from exc
        except URLError as exc:
            raise AlteriosRequestError(f"Network error: {exc.reason}") from exc

    def list_comments(
        self,
        entity_id: str,
        *,
        entity: str = "any",
        limit: int = 20,
        depth: int = 1,
        page: int = 1,
    ) -> AlteriosResponse:
        return self.request(
            "GET",
            "/api/v1/comments",
            params={"entity": entity, "entityId": entity_id, "limit": limit, "depth": depth, "page": page},
        )

    def add_comment(
        self,
        entity_id: str,
        body: str,
        *,
        entity: str = "any",
        parent_id: str | None = None,
    ) -> AlteriosResponse:
        if not entity_id.strip():
            raise ValueError("entity_id must not be empty")
        if not body.strip():
            raise ValueError("comment body must not be empty")
        payload: dict[str, Any] = {"entity": entity, "entityId": entity_id, "body": body}
        if parent_id:
            payload["parentId"] = parent_id
        return self.request("POST", "/api/v1/comments", body=payload)

    def view_data(
        self,
        view_id: str,
        *,
        limit: int = 20,
        offset: int = 0,
        content_id: str | None = None,
        data_id: list[str] | None = None,
        user_filters: dict[str, Any] | None = None,
    ) -> AlteriosResponse:
        body: dict[str, Any] = {"viewId": view_id, "limit": limit, "offset": offset}
        if content_id is not None:
            body["contentId"] = content_id
        if data_id is not None:
            body["dataId"] = data_id
        if user_filters is not None:
            body["userFilters"] = user_filters
        return self.request("POST", "/api/views/v2/get-data", body=body)

    def view_data_simplified(self, view_id: str, *, limit: int = 20, offset: int = 0) -> AlteriosResponse:
        return self.request("POST", "/api/views/v2/get-data-simplified", body={"viewId": view_id, "limit": limit, "offset": offset})

    def list_processes(
        self,
        *,
        diagram_id: str | None = None,
        content_id: str | None = None,
        process_id: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> AlteriosResponse:
        return self.request(
            "GET",
            "/api/processes/listandcount",
            params={
                "_id": process_id,
                "diagramId": diagram_id,
                "contentId": content_id,
                "limit": limit,
                "offset": offset,
            },
        )

    def list_tasks(
        self,
        *,
        diagram_id: str | None = None,
        content_id: str | None = None,
        process_id: str | None = None,
        task_id: str | None = None,
    ) -> AlteriosResponse:
        return self.request(
            "GET",
            "/api/tasks/",
            params={"_id": task_id, "diagramId": diagram_id, "contentId": content_id, "processId": process_id},
        )

    def start_process(
        self,
        diagram_id: str,
        *,
        content_id: str | None = None,
        params: dict[str, Any] | None = None,
        name: str | None = None,
        start_message_id: str | None = None,
        response_message_id: str | None = None,
        contents: list[dict[str, Any]] | None = None,
    ) -> AlteriosResponse:
        if not diagram_id.strip():
            raise ValueError("diagram_id must not be empty")
        body: dict[str, Any] = {"diagramId": diagram_id}
        if content_id is not None:
            body["contentId"] = content_id
        if params is not None:
            body["params"] = params
        if name is not None:
            body["name"] = name
        if start_message_id is not None:
            body["startMessageId"] = start_message_id
        if response_message_id is not None:
            body["responseMessageId"] = response_message_id
        if contents is not None:
            body["contents"] = contents
        return self.request("POST", "/api/processes", body=body)

    def complete_task(
        self,
        task_id: str,
        *,
        next_flow_id: str | None = None,
        process_content: dict[str, Any] | None = None,
        contents: list[dict[str, Any]] | None = None,
    ) -> AlteriosResponse:
        if not task_id.strip():
            raise ValueError("task_id must not be empty")
        body: dict[str, Any] = {"_id": task_id}
        if next_flow_id is not None:
            body["nextFlowId"] = next_flow_id
        if process_content is not None:
            body["processContent"] = process_content
        if contents is not None:
            body["contents"] = contents
        return self.request("DELETE", "/api/tasks/complete", body=body)

    def build_script_url(self, function: str) -> str:
        template = self.config.endpoint_template.strip()
        if not template:
            raise AlteriosConfigError("ALTERIOS_ENDPOINT_TEMPLATE is required")

        base_url = self.config.base_url.rstrip("/")
        try:
            rendered = template.format(base_url=base_url, function=quote(function, safe=""))
        except KeyError as exc:
            raise AlteriosConfigError(f"Unsupported endpoint template placeholder: {exc}") from exc

        if _looks_absolute_url(rendered):
            return rendered
        if not base_url:
            raise AlteriosConfigError("ALTERIOS_BASE_URL is required for a relative endpoint template")
        return f"{base_url}/{rendered.lstrip('/')}"

    def save_resource(self, collection: str, payload: dict[str, Any]) -> AlteriosResponse:
        body = strip_alterios_metadata(payload)
        resource_id = body.get("_id")
        if not resource_id:
            return self.request("POST", f"/api/{collection}", body=body)

        errors: list[str] = []
        for method, path in (
            ("PATCH", f"/api/{collection}/{path_segment(str(resource_id))}"),
            ("PUT", f"/api/{collection}/{path_segment(str(resource_id))}"),
            ("PUT", f"/api/{collection}"),
            ("POST", f"/api/{collection}"),
        ):
            try:
                return self.request(method, path, body=body)
            except AlteriosRequestError as exc:
                errors.append(str(exc))
        raise AlteriosRequestError(f"Update /api/{collection}/{resource_id} failed: {'; '.join(errors)}")

    def delete_resource(self, collection: str, resource_id: str) -> AlteriosResponse:
        if not resource_id.strip():
            raise ValueError("resource_id must not be empty")
        errors: list[str] = []
        for path, body in (
            (f"/api/{collection}/{path_segment(resource_id)}", {}),
            (f"/api/{collection}", {"_id": resource_id}),
        ):
            try:
                return self.request("DELETE", path, body=body)
            except AlteriosRequestError as exc:
                errors.append(str(exc))
        raise AlteriosRequestError(f"Delete /api/{collection}/{resource_id} failed: {'; '.join(errors)}")

    def _listandcount_item_by_id(self, path: str, item_id: str, label: str) -> AlteriosResponse:
        if not item_id.strip():
            raise ValueError("item_id must not be empty")
        response = self.request("GET", path, params={"_id": item_id, "limit": 1, "offset": 0})
        items = listandcount_items(response.body)
        if not items:
            raise AlteriosRequestError(f"{label} {item_id!r} was not found.")
        return AlteriosResponse(response.status_code, response.content_type, items[0])

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json; charset=utf-8",
            "lang": "ru",
        }
        if self.config.project_id:
            headers["projectid"] = self.config.project_id
        auth_value = self.config.api_token
        if self.config.auth_scheme:
            auth_value = f"{self.config.auth_scheme} {auth_value}"
        headers[self.config.auth_header] = auth_value
        return headers

    def _send(self, prepared: PreparedAlteriosRequest) -> AlteriosResponse:
        data = None
        if prepared.body is not None:
            data = json.dumps(prepared.body, ensure_ascii=False).encode("utf-8")

        request = Request(prepared.url, data=data, headers=prepared.headers, method=prepared.method)
        try:
            with urlopen(request, timeout=self.config.timeout_seconds) as response:
                response_body = response.read()
                content_type = response.headers.get("Content-Type", "")
                return AlteriosResponse(
                    status_code=response.status,
                    content_type=content_type,
                    body=parse_response_body(response_body, content_type),
                )
        except HTTPError as exc:
            content_type = exc.headers.get("Content-Type", "") if exc.headers else ""
            parsed_body = parse_response_body(exc.read(), content_type)
            raise AlteriosRequestError(f"HTTP {exc.code}: {safe_error(parsed_body)}") from exc
        except TimeoutError as exc:
            raise AlteriosRequestError("Network error: timed out") from exc
        except URLError as exc:
            raise AlteriosRequestError(f"Network error: {exc.reason}") from exc


def build_script_body(function: str, args: Any, body_style: str) -> Any:
    style = body_style.strip().lower()
    payload = {} if args is None else args
    if style == "rpc":
        return {"function": function, "args": payload}
    if style == "service":
        return {"service": function, "args": payload}
    if style == "params":
        return {"function": function, "params": payload}
    if style in {"manual_script", "execute_manual"}:
        if not looks_like_uuid(function):
            raise AlteriosConfigError("manual_script body style requires a script UUID")
        return {"_id": function, "args": payload}
    if style == "direct":
        return {"_id": function, "args": payload} if looks_like_uuid(function) else {"function": function, "args": payload}
    raise AlteriosConfigError("ALTERIOS_BODY_STYLE must be one of: rpc, service, params, direct, manual_script")


def encode_filter(value: Any) -> str:
    return quote(json.dumps(value, ensure_ascii=False, separators=(",", ":")), safe="")


def path_segment(value: str) -> str:
    return quote(value, safe="")


def parse_response_body(response_body: bytes, content_type: str) -> Any:
    if not response_body:
        return None
    text = response_body.decode("utf-8", errors="replace")
    if "json" in content_type.lower():
        return json.loads(text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def read_dotenv(path: str | Path) -> dict[str, str]:
    dotenv_path = Path(path)
    if not dotenv_path.exists():
        return {}

    values: dict[str, str] = {}
    for raw_line in dotenv_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
            value = value[1:-1]
        values[key] = value
    return values


def load_config_values(dotenv_path: str | Path | None = ".env") -> dict[str, str]:
    if dotenv_path == ".env":
        dotenv_path = os.environ.get("ALTERIOS_DOTENV_PATH", ".env")

    values: dict[str, str] = {}
    if dotenv_path is not None:
        values.update(read_dotenv(dotenv_path))
    values.update(os.environ)
    return values


def configured_profiles(
    dotenv_path: str | Path | None = ".env",
    *,
    selected_profile: str | None = None,
) -> dict[str, Any]:
    values = load_config_values(dotenv_path)
    effective_selected_profile = (values.get("ALTERIOS_PROFILE", "") if selected_profile is None else selected_profile).strip()
    profile_names = discover_profile_names(values, selected_profile=effective_selected_profile)
    profiles = []
    for profile_name in profile_names:
        config = AlteriosConfig.from_env(dotenv_path=dotenv_path, profile=profile_name)
        profiles.append(
            {
                "profile": profile_name or "<default>",
                "profile_argument": profile_name or None,
                "selected": _same_profile(profile_name, effective_selected_profile),
                "config": config.redacted(),
                "missing_for_instance_call": config.missing_for_instance_call(),
                "missing_for_project_call": config.missing_for_project_call(),
                "missing_for_script_call": config.missing_for_script_call(),
                "has_project_default": bool(config.project_id),
            }
        )

    return {
        "selected_profile": effective_selected_profile or None,
        "profile_count": len(profiles),
        "profiles": profiles,
    }


def discover_profile_names(values: dict[str, str], *, selected_profile: str | None = None) -> list[str]:
    profile_names: dict[str, str] = {}

    for raw_profile in _split_profile_list(values.get("ALTERIOS_PROFILES", "")):
        profile_names[normalize_profile_key(raw_profile)] = raw_profile

    effective_selected_profile = (values.get("ALTERIOS_PROFILE", "") if selected_profile is None else selected_profile).strip()
    if effective_selected_profile:
        profile_names.setdefault(normalize_profile_key(effective_selected_profile), effective_selected_profile)

    for key in values:
        match = PROFILE_KEY_RE.fullmatch(key)
        if not match:
            continue
        profile_key = match.group("profile")
        profile_names.setdefault(profile_key, profile_key.lower())

    if not profile_names and any(values.get(f"ALTERIOS_{suffix}", "").strip() for suffix in PROFILE_CONFIG_SUFFIXES):
        profile_names[""] = ""

    def sort_key(profile_name: str) -> tuple[int, str]:
        if _same_profile(profile_name, effective_selected_profile):
            return (0, profile_name.lower())
        return (1, profile_name.lower())

    return sorted(profile_names.values(), key=sort_key)


def _split_profile_list(value: str) -> list[str]:
    profiles = []
    for raw_item in re.split(r"[,;\s]+", value):
        item = raw_item.strip()
        if item:
            profiles.append(item)
    return profiles


def apply_profile_values(values: dict[str, str], profile: str) -> dict[str, str]:
    if not profile:
        return values

    profile_key = normalize_profile_key(profile)
    effective = dict(values)
    target_suffixes = {"BASE_URL", "API_TOKEN", "PROJECT_ID"}
    for suffix in PROFILE_CONFIG_SUFFIXES:
        profile_env_key = f"ALTERIOS_{profile_key}_{suffix}"
        if profile_env_key in values:
            effective[f"ALTERIOS_{suffix}"] = values[profile_env_key]
        elif suffix in target_suffixes:
            effective[f"ALTERIOS_{suffix}"] = ""
    return effective


def profile_env_key(profile: str, suffix: str) -> str:
    return f"ALTERIOS_{normalize_profile_key(profile)}_{suffix}" if profile else f"ALTERIOS_{suffix}"


def normalize_profile_key(profile: str) -> str:
    key = re.sub(r"[^A-Za-z0-9]+", "_", profile.strip()).strip("_").upper()
    if not key:
        raise AlteriosConfigError("ALTERIOS_PROFILE cannot be empty")
    return key


def redact_url_value(value: str) -> str:
    if not value:
        return value
    if "://" not in value:
        return _redact_sensitive_query_text(value)
    try:
        parsed = urlsplit(value)
    except ValueError:
        return "<redacted-url>"

    netloc = parsed.netloc
    if "@" in netloc:
        host = netloc.rsplit("@", 1)[1]
        netloc = f"<redacted>@{host}"

    query_pairs = []
    for key, item in parse_qsl(parsed.query, keep_blank_values=True):
        query_pairs.append((key, "<redacted>" if _is_sensitive_config_key(key) else item))
    query = urlencode(query_pairs)
    return urlunsplit((parsed.scheme, netloc, parsed.path, query, parsed.fragment))


def _redact_sensitive_query_text(value: str) -> str:
    if "?" not in value:
        return value
    prefix, query = value.split("?", 1)
    query_pairs = []
    for key, item in parse_qsl(query, keep_blank_values=True):
        query_pairs.append((key, "<redacted>" if _is_sensitive_config_key(key) else item))
    return prefix + "?" + urlencode(query_pairs)


def _is_sensitive_config_key(key: str) -> bool:
    normalized = key.lower().replace("-", "_")
    return _is_sensitive_key_name(normalized)


def _same_profile(left: str, right: str) -> bool:
    if not left and not right:
        return True
    if not left or not right:
        return False
    return normalize_profile_key(left) == normalize_profile_key(right)


def _is_sensitive_key_name(key: str) -> bool:
    normalized = key.lower().replace("-", "_")
    compact = normalized.replace("_", "")
    return (
        normalized in {"api_key", "apikey", "authorization", "secret", "token", "cookie", "set_cookie"}
        or compact in {"emailconfirmationcode", "emailverificationcode"}
        or "email" in normalized
        or "password" in normalized
        or normalized in {"author_name", "authorname"}
        or normalized == "project"
        or normalized in {"project_name", "projectname", "participants_ids", "telegram_support_group_ids"}
        or compact in {"participantsids", "telegramsupportgroupids"}
        or "secret" in normalized
        or compact.endswith("apikey")
        or normalized.endswith("_token")
    )


def redact_sensitive(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: "<redacted>" if _is_sensitive_key_name(str(key)) else redact_sensitive(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_sensitive(item) for item in value]
    return value


def safe_error(payload: Any) -> str:
    payload = redact_sensitive(payload)
    if isinstance(payload, dict):
        return json.dumps(
            {key: payload.get(key) for key in ("statusCode", "message", "error", "name", "_id") if key in payload},
            ensure_ascii=False,
        )
    if isinstance(payload, list):
        return f"list[{len(payload)}]"
    return str(payload)[:300]


def listandcount_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        if payload and isinstance(payload[0], list):
            return [item for item in payload[0] if isinstance(item, dict)]
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("items", "rows", "data", "results", "values"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    raise AlteriosRequestError("listandcount returned unexpected payload.")


def report_full_item(payload: Any) -> dict[str, Any] | None:
    if isinstance(payload, list):
        return payload[0] if payload and isinstance(payload[0], dict) else None
    if isinstance(payload, dict):
        for key in ("items", "rows", "data", "results", "values"):
            value = payload.get(key)
            if isinstance(value, list):
                return value[0] if value and isinstance(value[0], dict) else None
        return payload
    return None


def content_update_payload(
    existing: dict[str, Any],
    field_values: dict[str, Any],
    *,
    content_type_id: str | None = None,
    groups_ids: list[str] | None = None,
    name: str | None = None,
) -> dict[str, Any]:
    content_id = str(existing.get("_id") or "").strip()
    if not content_id:
        raise AlteriosRequestError("Content readback does not contain _id.")

    resolved_content_type_id = content_type_id or existing.get("contentTypeId")
    if not resolved_content_type_id:
        raise AlteriosRequestError("Content type id is required for content update.")

    fields = dict(existing.get("fields") or {})
    for field_name, value in field_values.items():
        if not str(field_name).strip():
            raise ValueError("field_values contains an empty field name")
        fields[str(field_name)] = normalize_content_field_value(value)

    payload: dict[str, Any] = {
        "_id": content_id,
        "contentTypeId": resolved_content_type_id,
        "fields": fields,
    }
    resolved_groups_ids = groups_ids if groups_ids is not None else existing.get("groupsIds")
    if resolved_groups_ids is not None:
        payload["groupsIds"] = resolved_groups_ids
    resolved_name = name if name is not None else existing.get("name")
    if resolved_name is not None:
        payload["name"] = resolved_name
    return payload


def strip_alterios_metadata(value: Any) -> Any:
    metadata_keys = {
        "apiKey",
        "author",
        "authorId",
        "authorName",
        "createdAt",
        "emailConfirmationCode",
        "lastUpdate",
        "password",
        "passwordRecoverCode",
        "token",
        "updatedBy",
        "version",
    }
    if isinstance(value, dict):
        return {key: strip_alterios_metadata(item) for key, item in value.items() if key not in metadata_keys}
    if isinstance(value, list):
        return [strip_alterios_metadata(item) for item in value]
    return value


def normalize_content_field_value(value: Any) -> list[Any]:
    return value if isinstance(value, list) else [value]


def build_multipart(boundary: str, field_name: str, filename: str, mime_type: str, data: bytes) -> bytes:
    safe_filename = filename.replace('"', "'")
    head_text = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="{field_name}"; filename="{safe_filename}"\r\n'
        f"Content-Type: {mime_type}\r\n\r\n"
    )
    tail_text = f"\r\n--{boundary}--\r\n"
    return head_text.encode("utf-8") + data + tail_text.encode("utf-8")


def looks_like_uuid(value: str) -> bool:
    return bool(re.fullmatch(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}", value))


def _looks_absolute_url(value: str) -> bool:
    return value.startswith("https://") or value.startswith("http://")


def _looks_like_execute_manual_url(value: str) -> bool:
    return "/api/scripts/execute-manual" in value
