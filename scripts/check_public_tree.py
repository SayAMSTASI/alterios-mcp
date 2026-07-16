from __future__ import annotations

import fnmatch
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ALLOWED_ENV_FILES = {".env.example"}
FORBIDDEN_PATHS = (
    "artifacts/*",
    "docs/project-status.md",
    "docs/*-evidence-*.md",
    "docs/*-evidence-*.json",
    "docs/form-surface-inventory.*",
    "docs/icon-usage-matrix.json",
    "docs/profile-smoke-matrix-*",
    "docs/script-bpmn-linkage.*",
    "scripts/*practice*",
    "tests/test_*practice*",
)
CONTENT_RULES = (
    (
        "private Alterios/Git domain",
        re.compile(r"(?i)\b(?:lims|git)\.(?!example(?:\.|$))[a-z0-9.-]+\.(?:ru|local)\b"),
    ),
    (
        "workspace UUID in URL",
        re.compile(
            r"(?i)/workspace/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-"
            r"[0-9a-f]{4}-[0-9a-f]{12}"
        ),
    ),
    ("browser session cookie", re.compile(r"(?i)(?:i_like_gitea|_csrf)=[^\s<]+")),
    ("authorization token", re.compile(r"(?i)Bearer[ \t]+[A-Za-z0-9._-]{20,}")),
    ("private key", re.compile(r"-----BEGIN (?:RSA |OPENSSH )?PRIVATE KEY-----")),
    (
        "personal workspace path",
        re.compile(r"(?i)C:\\Users\\(?!<user>(?:\\|$)|username(?:\\|$)|example(?:\\|$))[^\\\r\n]+"),
    ),
)
UUID_RE = re.compile(
    r"(?i)[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
)


def tracked_and_unignored_files() -> list[Path]:
    completed = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=ROOT,
        capture_output=True,
        check=True,
    )
    return [ROOT / item.decode("utf-8") for item in completed.stdout.split(b"\0") if item]


def scan_path(path: Path) -> list[str]:
    relative = path.relative_to(ROOT).as_posix()
    if not path.exists():
        return []
    issues: list[str] = []
    if relative.startswith(".env") and relative not in ALLOWED_ENV_FILES:
        issues.append(f"{relative}: forbidden environment file")
    for pattern in FORBIDDEN_PATHS:
        if fnmatch.fnmatch(relative, pattern):
            issues.append(f"{relative}: forbidden project-artifact path ({pattern})")
    if not path.is_file() or path.stat().st_size > 5 * 1024 * 1024:
        return issues
    if relative == "scripts/check_public_tree.py":
        return issues
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return issues
    for description, pattern in CONTENT_RULES:
        match = pattern.search(text)
        if match:
            line = text.count("\n", 0, match.start()) + 1
            issues.append(f"{relative}:{line}: {description}")
    if relative.startswith("docs/"):
        for match in UUID_RE.finditer(text):
            line_start = text.rfind("\n", 0, match.start()) + 1
            line_end = text.find("\n", match.end())
            line_text = text[line_start : line_end if line_end >= 0 else len(text)]
            if "admin.stimulsoft.com/documentation" not in line_text:
                line = text.count("\n", 0, match.start()) + 1
                issues.append(f"{relative}:{line}: UUID in public documentation")
                break
    return issues


def main() -> int:
    issues = [issue for path in tracked_and_unignored_files() for issue in scan_path(path)]
    if issues:
        print("Public repository check failed:")
        for issue in issues:
            print(f"- {issue}")
        return 1
    print("Public repository check passed: no forbidden project data or secret patterns found.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
