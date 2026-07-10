from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "install_repo_skills.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("install_repo_skills", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_plan_install_lists_repo_skills(tmp_path: Path) -> None:
    module = _load_module()
    plans = module.plan_install(ROOT / "skills", tmp_path)

    assert len(plans) == 8
    assert {item.action for item in plans} == {"install"}
    assert {item.name for item in plans} == {
        "alterios-project-base-inventory",
        "alterios-form-view-surface",
        "alterios-ui-icons-and-actions",
        "alterios-script-bpmn-flow",
        "alterios-write-tools",
        "alterios-stimulsoft-project-db",
        "alterios-safety-verifier",
        "alterios-pm-control-loop",
    }


def test_execute_plan_copies_and_then_skips_existing(tmp_path: Path) -> None:
    module = _load_module()
    plans = module.plan_install(ROOT / "skills", tmp_path)
    module.execute_plan(plans, tmp_path)

    for item in plans:
        installed_skill = tmp_path / item.name
        assert (installed_skill / "SKILL.md").is_file()
        assert (installed_skill / "agents" / "openai.yaml").is_file()
        source_map = installed_skill / "references" / "source-map.md"
        assert source_map.is_file()
        assert "../../../" not in source_map.read_text(encoding="utf-8")

    second_plan = module.plan_install(ROOT / "skills", tmp_path)
    assert {item.action for item in second_plan} == {"skip"}


def test_replace_plan_marks_existing_targets(tmp_path: Path) -> None:
    module = _load_module()
    plans = module.plan_install(ROOT / "skills", tmp_path)
    module.execute_plan(plans, tmp_path)

    replace_plan = module.plan_install(ROOT / "skills", tmp_path, replace=True)

    assert {item.action for item in replace_plan} == {"replace"}
