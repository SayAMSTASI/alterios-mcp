from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ICON_DIR = ROOT / "assets" / "icons" / "project-public"
MANIFEST_PATH = ICON_DIR / "manifest.json"
CATALOG_PATH = ROOT / "docs" / "alterios-icons-and-actions-catalog.md"


def test_project_icon_library_manifest_matches_svg_files() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    icons = manifest["icons"]

    assert manifest["icon_count"] == len(icons) == 39
    assert manifest["rules"]["catalog"] == "docs/alterios-icons-and-actions-catalog.md"
    assert manifest["rules"]["svg_size"]
    assert manifest["rules"]["svg_color"]

    filenames = {icon["filename"] for icon in icons}
    assert filenames == {path.name for path in ICON_DIR.glob("*.svg")}

    for icon in icons:
        path = ICON_DIR / icon["filename"]
        data = path.read_bytes()
        assert icon["bytes"] == len(data)
        assert icon["sha256"] == hashlib.sha256(data).hexdigest()
        assert icon["usage_hint"]


def test_project_icon_library_svg_dimensions_and_color_are_valid() -> None:
    for path in ICON_DIR.glob("*.svg"):
        text = path.read_text(encoding="utf-8")
        assert re.search(r'width="20px"', text), path.name
        assert re.search(r'height="20px"', text), path.name
        assert re.search(r'viewBox="0 -960 960 960"', text), path.name

        colors = {color.upper() for color in re.findall(r"#[0-9A-Fa-f]{6}", text)}
        assert colors == {"#4B77D1"}, path.name


def test_icon_catalog_contains_visual_previews_for_every_icon() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    catalog = CATALOG_PATH.read_text(encoding="utf-8")

    for icon in manifest["icons"]:
        preview = f"![{icon['semantic']}](../assets/icons/project-public/{icon['filename']})"
        assert preview in catalog
