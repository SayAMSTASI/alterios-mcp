from __future__ import annotations

import base64
import json
import subprocess
from pathlib import Path
from unittest.mock import patch

from alterios_mcp.printable_render import render_printable_pdf


def test_render_printable_pdf_writes_verified_artifact(tmp_path: Path) -> None:
    reports_script = tmp_path / "stimulsoft.reports.pack.js"
    reports_script.write_text("runtime", encoding="utf-8")
    pdf = b"%PDF-1.7\nverified\n%%EOF"
    completed = subprocess.CompletedProcess(
        args=["node"],
        returncode=0,
        stdout=json.dumps({"pageCount": 2, "pdfBase64": base64.b64encode(pdf).decode("ascii")}),
        stderr="",
    )
    output = tmp_path / "evidence.pdf"

    with (
        patch("alterios_mcp.printable_render._find_node", return_value=Path("node.exe")),
        patch("alterios_mcp.printable_render._find_chromium", return_value=Path("chrome.exe")),
        patch("alterios_mcp.printable_render._find_node_path", return_value=[tmp_path]),
        patch("alterios_mcp.printable_render.subprocess.run", return_value=completed) as run,
    ):
        result = render_printable_pdf(
            {"Pages": {"0": {"Ident": "StiPage"}}},
            rows=[{"name": ["A"], "count": [10], "tags": ["x", "y"], "empty": []}],
            reports_script=reports_script,
            output_path=output,
        )

    assert output.read_bytes() == pdf
    assert result["ok"] is True
    assert result["page_count"] == 2
    assert result["pdf_size"] == len(pdf)
    assert len(result["pdf_sha256"]) == 64
    render_input = json.loads(run.call_args.kwargs["input"])
    assert render_input["rows"] == [{"name": "A", "count": 10, "tags": "x; y", "empty": ""}]


def test_ux_contract_tool_is_machine_readable() -> None:
    from alterios_mcp.server import alterios_ux_contract

    result = alterios_ux_contract()

    assert result["version"]
    assert "field_footnote_requires_date" in result["blocking_form_issue_codes"]
    assert "fresh_runtime_fingerprint" in result["scenario_apply_requires"]
