from __future__ import annotations

from alterios_mcp import server


def test_local_workboard_config_uses_explicit_base_dir(tmp_path) -> None:
    result = server.local_workboard_config(base_dir=str(tmp_path))

    assert result["config"]["base_dir"] == str(tmp_path)
    assert result["exists"] is True
    assert result["required_execution_gates"] == ["dry_run=false"]


def test_local_workboard_create_item_dry_run_does_not_write(tmp_path) -> None:
    result = server.local_workboard_create_item(
        title="Test local item",
        body="Private body",
        status="ready",
        kind="feature",
        sprint="2026-07-S1",
        base_dir=str(tmp_path),
    )

    assert result["dry_run"] is True
    assert result["will_execute"] is False
    assert result["payload"]["status"] == "ready"
    assert not (tmp_path / "issues").exists()


def test_local_workboard_create_item_execution_writes_private_files(tmp_path) -> None:
    result = server.local_workboard_create_item(
        title="Test local item",
        body="Private body",
        status="ready",
        kind="feature",
        sprint="2026-07-S1",
        labels=["area:mcp"],
        assignee="PM",
        base_dir=str(tmp_path),
        dry_run=False,
    )

    item_id = result["payload"]["item_id"]
    item_dir = tmp_path / "issues" / item_id
    assert result["dry_run"] is False
    assert (item_dir / "brief.md").exists()
    assert (item_dir / "agent-reports.md").exists()
    assert (item_dir / "evidence").is_dir()
    assert "| `ready` | `feature` | 2026-07-S1 | PM |" in (tmp_path / "index.md").read_text(encoding="utf-8")

    listed = server.local_workboard_list_items(status="ready", sprint="2026-07-S1", base_dir=str(tmp_path))
    assert [item["id"] for item in listed["items"]] == [item_id]
    assert listed["items"][0]["title"] == "Test local item"


def test_local_workboard_agent_report_appends_to_item(tmp_path) -> None:
    created = server.local_workboard_create_item(
        title="Report target",
        body="Private body",
        base_dir=str(tmp_path),
        dry_run=False,
    )
    item_id = created["payload"]["item_id"]

    result = server.local_workboard_add_agent_report(
        item_id=item_id,
        role="Verifier",
        scope="Local fallback",
        findings="Checked files",
        verification="Unit test",
        base_dir=str(tmp_path),
        dry_run=False,
    )

    report_path = tmp_path / "issues" / item_id / "agent-reports.md"
    text = report_path.read_text(encoding="utf-8")
    assert result["response"]["appended"] is True
    assert "Verifier" in text
    assert "Checked files" in text
