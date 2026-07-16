from __future__ import annotations

import json

from alterios_mcp.ui_flow import analyze_ui_flow, classify_api_call, main


def test_analyze_har_redacts_secrets_and_classifies_routes() -> None:
    payload = {
        "log": {
            "entries": [
                _har_entry(
                    "GET",
                    "https://lims.example.local/assets/app.js",
                    status=200,
                ),
                _har_entry(
                    "GET",
                    "https://lims.example.local/api/contents/listandcount?projectid=raw-project-id&token=secret-token",
                    request_headers=[
                        {"name": "Authorization", "value": "Bearer private"},
                        {"name": "Cookie", "value": "session=private"},
                        {"name": "projectid", "value": "raw-project-id"},
                    ],
                    response_body={"rows": [{"_id": "content-1234567890"}]},
                    status=200,
                ),
                _har_entry(
                    "POST",
                    "https://lims.example.local/api/views/v2/get-data",
                    request_body={"viewId": "view-1234567890", "contentId": "content-1234567890"},
                    response_body={"data": [{"name": "Private Name"}]},
                    status=200,
                ),
                _har_entry(
                    "PATCH",
                    "https://lims.example.local/api/contents/save",
                    request_body={
                        "_id": "content-1234567890",
                        "fields": {"person": "Private Name"},
                        "password": "private-password",
                    },
                    response_body={"_id": "content-1234567890", "ok": True},
                    status=0,
                ),
                _har_entry(
                    "DELETE",
                    "https://lims.example.local/api/tasks/complete",
                    request_body={"_id": "task_1234567890", "nextFlowId": "flow_1234567890"},
                    response_body={"ok": True},
                    status=0,
                ),
            ]
        }
    }

    analysis = analyze_ui_flow(payload, profile="primary", project_id="project-1234567890", scenario="form-open")

    assert analysis["source_type"] == "har"
    assert analysis["summary"]["total_events"] == 4
    assert analysis["redaction_report"]["dropped_non_api_events"] == 1
    assert analysis["redaction_report"]["redacted_headers"] == 2
    assert analysis["redaction_report"]["redacted_query_values"] == 1
    assert analysis["redaction_report"]["stable_id_count"] >= 4

    by_path = {(flow["method"], flow["path"]): flow for flow in analysis["flows"]}
    assert by_path[("GET", "/api/contents/listandcount")]["risk_level"] == "read"
    assert by_path[("POST", "/api/views/v2/get-data")]["risk_level"] == "read"
    assert by_path[("PATCH", "/api/contents/save")]["risk_level"] == "write"
    assert by_path[("DELETE", "/api/tasks/complete")]["risk_level"] == "workflow_side_effect"
    assert "workflow" in by_path[("DELETE", "/api/tasks/complete")]["labels"]
    assert by_path[("PATCH", "/api/contents/save")]["request"]["body"]["password"] == "<redacted>"
    assert by_path[("PATCH", "/api/contents/save")]["request"]["body"]["fields"]["person"] == "<redacted>"
    assert by_path[("GET", "/api/contents/listandcount")]["request"]["headers"]["authorization"] == "<redacted>"
    assert analysis["summary"]["successful_write_like_route_count"] == 0


def test_classify_known_read_post_and_unknown_write_fallback() -> None:
    read_post = classify_api_call("POST", "/api/views/v2/get-data-simplified")
    unknown_write = classify_api_call("POST", "/api/new-undocumented-action")

    assert read_post["risk_level"] == "read"
    assert read_post["requires_write_gate"] is False
    assert unknown_write["risk_level"] == "write"
    assert unknown_write["requires_write_gate"] is True
    assert unknown_write["classification_source"] == "method_fallback"


def test_file_and_comment_routes_have_labels() -> None:
    file_read = classify_api_call("GET", "/api/file/list")
    file_write = classify_api_call("POST", "/api/file/upload/field")
    comment_delete = classify_api_call("DELETE", "/api/v1/comments/comment-1234567890")

    assert file_read["labels"] == ["file", "read"]
    assert file_write["risk_level"] == "write"
    assert set(file_write["labels"]) == {"file", "write"}
    assert comment_delete["risk_level"] == "destructive"
    assert set(comment_delete["labels"]) == {"comment", "destructive"}


def test_simple_event_input_is_json_serializable() -> None:
    analysis = analyze_ui_flow(
        [
            {
                "method": "GET",
                "url": "/api/v1/comments?entity=content&entityId=content-1234567890",
                "status": 200,
                "headers": {"x-api-key": "private"},
                "response_body": [{"body": "Private comment"}],
            }
        ],
        scenario="comments-open",
    )

    assert analysis["source_type"] == "events"
    assert analysis["flows"][0]["labels"] == ["comment", "read"]
    assert analysis["flows"][0]["request"]["headers"]["x-api-key"] == "<redacted>"
    assert json.loads(json.dumps(analysis, sort_keys=True)) == analysis


def test_cli_prints_summary(tmp_path, capsys) -> None:
    input_path = tmp_path / "flow.json"
    input_path.write_text(
        json.dumps(
            [
                {
                    "method": "POST",
                    "url": "/api/views/v2/get-data",
                    "status": 200,
                    "body": {"viewId": "view-1234567890"},
                }
            ]
        ),
        encoding="utf-8",
    )

    assert main([str(input_path), "--scenario", "view-open"]) == 0
    output = capsys.readouterr().out

    assert "events: 1" in output
    assert "write-gated routes: 0" in output


def _har_entry(
    method: str,
    url: str,
    *,
    request_headers: list[dict[str, str]] | None = None,
    request_body: object | None = None,
    response_body: object | None = None,
    status: int,
) -> dict[str, object]:
    request: dict[str, object] = {
        "method": method,
        "url": url,
        "headers": request_headers or [],
    }
    if request_body is not None:
        request["postData"] = {
            "mimeType": "application/json",
            "text": json.dumps(request_body),
        }
    return {
        "request": request,
        "response": {
            "status": status,
            "headers": [{"name": "Content-Type", "value": "application/json"}],
            "content": {
                "mimeType": "application/json",
                "text": json.dumps(response_body) if response_body is not None else "",
            },
        },
    }
