from __future__ import annotations

import json
import os
import re
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

    def view_entities(self, view_id: str) -> AlteriosResponse:
        return self.request("GET", f"/api/view-entities/by-view/{path_segment(view_id)}")

    def view_fields_populated(self, view_id: str) -> AlteriosResponse:
        return self.request("GET", f"/api/view-fields/populated/{path_segment(view_id)}")

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
    return normalized in {"api_key", "apikey", "authorization", "password", "secret", "token"} or normalized.endswith("_token")


def _same_profile(left: str, right: str) -> bool:
    if not left and not right:
        return True
    if not left or not right:
        return False
    return normalize_profile_key(left) == normalize_profile_key(right)


def redact_sensitive(value: Any) -> Any:
    sensitive_keys = {"apikey", "api_key", "authorization", "password", "token"}
    if isinstance(value, dict):
        return {
            key: "<redacted>" if key.lower() in sensitive_keys else redact_sensitive(item)
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


def looks_like_uuid(value: str) -> bool:
    return bool(re.fullmatch(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}", value))


def _looks_absolute_url(value: str) -> bool:
    return value.startswith("https://") or value.startswith("http://")


def _looks_like_execute_manual_url(value: str) -> bool:
    return "/api/scripts/execute-manual" in value
