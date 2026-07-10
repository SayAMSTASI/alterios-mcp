from __future__ import annotations

import argparse
import json
import os
import re
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Sequence


REQUIRED_SKILL_FILES = (
    "SKILL.md",
    "agents/openai.yaml",
    "references/source-map.md",
)

SOURCE_MAP_PATH_RE = re.compile(r"`([^`]+)`")


@dataclass(frozen=True)
class SkillInstallPlan:
    name: str
    source: str
    target: str
    action: str
    reason: str


def default_target_root() -> Path:
    codex_home = os.environ.get("CODEX_HOME")
    if codex_home:
        return Path(codex_home) / "skills"
    return Path.home() / ".codex" / "skills"


def validate_skill_dir(path: Path) -> None:
    if not path.is_dir():
        raise ValueError(f"skill source is not a directory: {path}")
    for rel_path in REQUIRED_SKILL_FILES:
        required = path / rel_path
        if not required.is_file():
            raise ValueError(f"skill {path.name} is missing {rel_path}")


def iter_skill_sources(source_root: Path) -> list[Path]:
    if not source_root.is_dir():
        raise ValueError(f"source root is not a directory: {source_root}")
    skill_dirs = sorted(path for path in source_root.iterdir() if path.is_dir())
    if not skill_dirs:
        raise ValueError(f"source root has no skill directories: {source_root}")
    for skill_dir in skill_dirs:
        validate_skill_dir(skill_dir)
    return skill_dirs


def _is_relative_to(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent)
    except ValueError:
        return False
    return True


def plan_install(source_root: Path, target_root: Path, *, replace: bool = False) -> list[SkillInstallPlan]:
    source_root = source_root.resolve()
    target_root = target_root.resolve()
    plans: list[SkillInstallPlan] = []
    for skill_dir in iter_skill_sources(source_root):
        target_dir = target_root / skill_dir.name
        if target_dir.exists() and not replace:
            action = "skip"
            reason = "target exists; pass --replace to overwrite"
        elif target_dir.exists():
            action = "replace"
            reason = "target exists and --replace was provided"
        else:
            action = "install"
            reason = "target does not exist"
        plans.append(
            SkillInstallPlan(
                name=skill_dir.name,
                source=str(skill_dir),
                target=str(target_dir),
                action=action,
                reason=reason,
            )
        )
    return plans


def execute_plan(plans: Sequence[SkillInstallPlan], target_root: Path) -> None:
    target_root = target_root.resolve()
    target_root.mkdir(parents=True, exist_ok=True)
    for item in plans:
        if item.action == "skip":
            continue
        source = Path(item.source).resolve()
        target = Path(item.target).resolve()
        if not _is_relative_to(target, target_root):
            raise ValueError(f"refusing to write outside target root: {target}")
        if item.action == "replace" and target.exists():
            shutil.rmtree(target)
        shutil.copytree(source, target)
        rewrite_installed_source_map(source, target)


def rewrite_installed_source_map(source_skill_dir: Path, target_skill_dir: Path) -> None:
    source_map = source_skill_dir / "references" / "source-map.md"
    target_map = target_skill_dir / "references" / "source-map.md"
    source_base = source_map.parent
    lines: list[str] = []
    for line in target_map.read_text(encoding="utf-8").splitlines():
        if not line.startswith("- `"):
            lines.append(line)
            continue

        def replace_match(match: re.Match[str]) -> str:
            raw_path = match.group(1)
            resolved = (source_base / raw_path).resolve()
            if not resolved.exists():
                return match.group(0)
            return f"`{resolved}`"

        lines.append(SOURCE_MAP_PATH_RE.sub(replace_match, line, count=1))
    target_map.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Install repo-owned Codex skills from this repository.")
    parser.add_argument("--source", default="skills", help="Source skills directory. Defaults to ./skills.")
    parser.add_argument(
        "--target",
        default=None,
        help="Target skills directory. Defaults to $CODEX_HOME/skills or ~/.codex/skills.",
    )
    parser.add_argument("--replace", action="store_true", help="Replace existing target skill directories.")
    parser.add_argument("--execute", action="store_true", help="Actually copy skills. Default is dry-run.")
    parser.add_argument("--json", action="store_true", help="Print JSON output.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    source_root = Path(args.source)
    target_root = Path(args.target) if args.target else default_target_root()
    plans = plan_install(source_root, target_root, replace=args.replace)
    if args.execute:
        execute_plan(plans, target_root)
    result = {
        "dry_run": not args.execute,
        "source_root": str(source_root.resolve()),
        "target_root": str(target_root.resolve()),
        "replace": bool(args.replace),
        "skills": [asdict(item) for item in plans],
    }
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        mode = "DRY-RUN" if result["dry_run"] else "EXECUTE"
        print(f"{mode}: {len(plans)} skills from {result['source_root']} to {result['target_root']}")
        for item in plans:
            print(f"- {item.action}: {item.name} ({item.reason})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
