from __future__ import annotations

from typing import Any

from alterios_mcp.scenarios import reports


class FakeResponse:
    def __init__(self, body: Any, status_code: int = 200) -> None:
        self.body = body
        self.status_code = status_code

    def as_dict(self) -> dict[str, Any]:
        return {"status_code": self.status_code, "content_type": "application/json", "body": self.body}


class FakeClient:
    def __init__(self) -> None:
        template = {
            "Pages": {
                "0": {
                    "Ident": "StiPage",
                    "Width": 800,
                    "Height": 1100,
                    "Components": {},
                }
            },
            "Dictionary": {
                "Databases": {
                    "0": {
                        "ServiceName": "Project Database",
                        "ConnectionStringEncrypted": "encrypted",
                    }
                }
            },
        }
        self.report = {"_id": "report-1", "name": "Printable", "type": "report", "template": template}
        self.form = {
            "_id": "form-1",
            "name": "Report form",
            "tabs": [
                {
                    "name": "Печать",
                    "rows": [
                        {
                            "cells": [
                                {
                                    "type": "report",
                                    "params": {"reportId": "report-1", "openId": True},
                                }
                            ]
                        }
                    ],
                }
            ],
        }

    def report_by_id(self, report_id: str) -> FakeResponse:
        assert report_id == "report-1"
        return FakeResponse(self.report)

    def view_data_simplified(self, view_id: str, *, limit: int, offset: int) -> FakeResponse:
        assert view_id == "view-1"
        return FakeResponse([{"name": "row"}])

    def form_by_id(self, form_id: str) -> FakeResponse:
        assert form_id == "form-1"
        return FakeResponse(self.form)


def test_report_viewer_diagnostic_separates_all_evidence_layers(monkeypatch) -> None:
    monkeypatch.setattr(reports, "_client", lambda profile, project_id: FakeClient())

    result = reports.alterios_diagnose_report_viewer(
        report_id="report-1",
        source_view_id="view-1",
        form_id="form-1",
        tab_name="Печать",
        expected_mode="printable",
        expected_open_id=True,
        viewer_evidence={
            "container_found": True,
            "container_visible": True,
            "width": 1024,
            "height": 768,
            "child_count": 4,
            "blocking_errors": [],
            "screenshot_path": "private/viewer.png",
        },
    )

    assert result["summary"]["status"] == "ready"
    assert result["detected_mode"] == "report"
    assert result["source"]["row_count"] == 1
    assert result["form_binding"]["cell_count"] == 1
    assert result["browser_viewer"]["ok"] is True


def test_report_viewer_diagnostic_marks_missing_browser_evidence_as_warning(monkeypatch) -> None:
    monkeypatch.setattr(reports, "_client", lambda profile, project_id: FakeClient())

    result = reports.alterios_diagnose_report_viewer(
        report_id="report-1",
        expected_mode="report",
    )

    assert result["summary"]["ok"] is True
    assert result["summary"]["status"] == "warning"
    assert "browser_viewer_evidence_not_collected" in result["summary"]["warnings"]
