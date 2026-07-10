from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILLS_DIR = ROOT / "skills"

EXPECTED_SKILLS = {
    "alterios-project-base-inventory",
    "alterios-form-view-surface",
    "alterios-ui-icons-and-actions",
    "alterios-script-bpmn-flow",
    "alterios-write-tools",
    "alterios-stimulsoft-project-db",
    "alterios-safety-verifier",
    "alterios-pm-control-loop",
}


def _frontmatter(text: str) -> dict[str, str]:
    assert text.startswith("---\n")
    end = text.index("\n---", 4)
    fields: dict[str, str] = {}
    for line in text[4:end].splitlines():
        if not line.strip():
            continue
        key, value = line.split(":", 1)
        fields[key.strip()] = value.strip()
    return fields


def test_repo_owned_skills_have_required_structure() -> None:
    assert {path.name for path in SKILLS_DIR.iterdir() if path.is_dir()} == EXPECTED_SKILLS

    for skill_name in EXPECTED_SKILLS:
        skill_dir = SKILLS_DIR / skill_name
        skill_md = skill_dir / "SKILL.md"
        openai_yaml = skill_dir / "agents" / "openai.yaml"
        source_map = skill_dir / "references" / "source-map.md"

        assert skill_md.is_file(), skill_name
        assert openai_yaml.is_file(), skill_name
        assert source_map.is_file(), skill_name

        text = skill_md.read_text(encoding="utf-8")
        metadata = _frontmatter(text)
        assert metadata["name"] == skill_name
        assert len(metadata["description"]) > 80
        assert "TODO" not in text
        assert "references/source-map.md" in text

        interface = openai_yaml.read_text(encoding="utf-8")
        assert f"Use ${skill_name}" in interface


def test_skill_source_maps_point_to_existing_files() -> None:
    for source_map in SKILLS_DIR.glob("*/references/source-map.md"):
        for line in source_map.read_text(encoding="utf-8").splitlines():
            if not line.startswith("- `"):
                continue
            rel_path = line.split("`", 2)[1]
            target = (source_map.parent / rel_path).resolve()
            assert target.exists(), f"{source_map}: missing {rel_path}"
