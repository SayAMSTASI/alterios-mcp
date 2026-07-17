from __future__ import annotations

import tomllib
from pathlib import Path

from alterios_mcp import __version__


ROOT = Path(__file__).parents[1]


def test_release_version_and_console_scripts_are_synchronized() -> None:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    project = pyproject["project"]
    scripts = project["scripts"]

    assert project["version"] == __version__ == "0.2.4"
    assert scripts["alterios-mcp"] == "alterios_mcp.server:main"
    assert scripts["alterios-doctor"] == "alterios_mcp.doctor:main"
    assert scripts["alterios-suggest-fixes"] == "alterios_mcp.suggest_fixes:main"
    assert scripts["alterios-release-smoke"] == "alterios_mcp.release_smoke:main"


def test_release_workflow_and_management_script_cover_delivery_contract() -> None:
    release_workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    manager = (ROOT / "scripts" / "manage_release.ps1").read_text(encoding="utf-8")

    assert 'tags:' in release_workflow
    assert 'python -m pip install -e ".[dev]"' in release_workflow
    assert 'python scripts/verify_release_wheel.py dist/*.whl' in release_workflow
    assert 'cp scripts/manage_release.ps1 dist/manage_release.ps1' in release_workflow
    assert 'SHA256SUMS.txt' in release_workflow
    assert 'gh release create' in release_workflow
    assert '[ValidateSet("Check", "Install", "Update", "Rollback", "Solutions")]' in manager
    assert 'Resolve-ReleaseWheel' in manager
    assert 'Get-ExpectedChecksum' in manager
    assert 'SHA256SUMS.txt' in manager
    assert 'Save-PreviousReleaseWheel' in manager
    assert 'Invoke-PreUpdateCheck' in manager
    assert 'A verified rollback wheel could not be prepared' in manager
    assert 'Invoke-LatestManagerIfNeeded' in manager
    assert 'StopRunningMcp' in manager
    assert 'alterios-doctor' in manager
    assert 'alterios-suggest-fixes' in manager
    assert 'alterios-release-smoke' in manager
