from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


BACKGROUND_IDENTS = {
    "StiHorizontalLinePrimitive",
    "StiLinePrimitive",
    "StiRectanglePrimitive",
    "StiRoundedRectanglePrimitive",
    "StiShape",
    "StiShapeElement",
    "StiVerticalLinePrimitive",
}

EPSILON = 0.001


@dataclass(frozen=True)
class Rect:
    left: float
    top: float
    width: float
    height: float

    @property
    def right(self) -> float:
        return self.left + self.width

    @property
    def bottom(self) -> float:
        return self.top + self.height

    @property
    def area(self) -> float:
        return max(0.0, self.width) * max(0.0, self.height)

    def intersection_area(self, other: "Rect") -> float:
        width = max(0.0, min(self.right, other.right) - max(self.left, other.left))
        height = max(0.0, min(self.bottom, other.bottom) - max(self.top, other.top))
        return width * height

    def horizontal_overlap(self, other: "Rect") -> bool:
        return min(self.right, other.right) - max(self.left, other.left) > EPSILON

    def to_dict(self) -> dict[str, float]:
        return {"left": self.left, "top": self.top, "width": self.width, "height": self.height}


@dataclass(frozen=True)
class ComponentRef:
    path: str
    parent_path: str
    ident: str
    name: str
    rect: Rect | None
    raw: dict[str, Any]
    page_width: float | None
    page_height: float | None

    @property
    def label(self) -> str:
        return self.name or self.ident or self.path


@dataclass(frozen=True)
class LayoutIssue:
    severity: str
    code: str
    path: str
    message: str
    details: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity,
            "code": self.code,
            "path": self.path,
            "message": self.message,
            "details": self.details,
        }


def analyze_stimulsoft_layout(
    report_or_template: Any,
    *,
    overlap_tolerance: float = 0.05,
) -> dict[str, Any]:
    """Analyze a Stimulsoft report/dashboard JSON template for layout risks."""
    template = normalize_template(report_or_template)
    components = collect_components(template)
    issues: list[LayoutIssue] = []

    for component in components:
        if component.rect is None:
            continue
        issues.extend(validate_component_bounds(component))

    by_parent: dict[str, list[ComponentRef]] = {}
    for component in components:
        if component.rect and is_visible(component.raw):
            by_parent.setdefault(component.parent_path, []).append(component)

    for siblings in by_parent.values():
        visible = [component for component in siblings if not is_background_component(component)]
        issues.extend(find_overlaps(visible, overlap_tolerance=overlap_tolerance))
        issues.extend(find_dynamic_height_risks(visible))
        issues.extend(find_mixed_row_growth(visible))

    issue_dicts = [issue.to_dict() for issue in issues]
    return {
        "ok": not any(issue.severity == "error" for issue in issues),
        "component_count": len(components),
        "issue_count": len(issue_dicts),
        "issues_by_severity": count_by(issue_dicts, "severity"),
        "issues_by_code": count_by(issue_dicts, "code"),
        "issues": issue_dicts,
    }


def normalize_template(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        value = json.loads(value)
    if not isinstance(value, dict):
        raise ValueError("Stimulsoft template must be a JSON object or JSON string.")
    if "template" in value and "Pages" not in value:
        template = value.get("template")
        if isinstance(template, str):
            template = json.loads(template)
        if not isinstance(template, dict):
            raise ValueError("Report object has no parseable template object.")
        return template
    return value


def collect_components(template: dict[str, Any]) -> list[ComponentRef]:
    pages = template.get("Pages") or {}
    components: list[ComponentRef] = []
    for page_key, page in iter_items(pages):
        if not isinstance(page, dict):
            continue
        page_path = f"Pages/{page_key}"
        page_width = parse_number(page.get("Width") or page.get("PageWidth"))
        page_height = parse_number(page.get("Height") or page.get("PageHeight"))
        components.extend(
            collect_components_from_container(
                page,
                parent_path=page_path,
                page_width=page_width,
                page_height=page_height,
            )
        )
    return components


def collect_components_from_container(
    container: dict[str, Any],
    *,
    parent_path: str,
    page_width: float | None,
    page_height: float | None,
) -> list[ComponentRef]:
    output: list[ComponentRef] = []
    for key, component in iter_items(container.get("Components") or {}):
        if not isinstance(component, dict):
            continue
        path = f"{parent_path}/Components/{key}"
        output.append(
            ComponentRef(
                path=path,
                parent_path=parent_path,
                ident=str(component.get("Ident") or ""),
                name=str(component.get("Name") or ""),
                rect=parse_rect(component),
                raw=component,
                page_width=page_width,
                page_height=page_height,
            )
        )
        output.extend(
            collect_components_from_container(
                component,
                parent_path=path,
                page_width=page_width,
                page_height=page_height,
            )
        )
    return output


def validate_component_bounds(component: ComponentRef) -> list[LayoutIssue]:
    rect = component.rect
    if rect is None:
        return []
    issues: list[LayoutIssue] = []
    if rect.width <= 0 or rect.height <= 0:
        issues.append(
            LayoutIssue(
                "error",
                "non_positive_size",
                component.path,
                "Component has zero or negative width/height.",
                {"component": component.label, "rect": rect.to_dict()},
            )
        )
    if rect.left < -EPSILON or rect.top < -EPSILON:
        issues.append(
            LayoutIssue(
                "warning",
                "negative_position",
                component.path,
                "Component starts outside the parent/page coordinate area.",
                {"component": component.label, "rect": rect.to_dict()},
            )
        )
    if component.page_width and rect.right > component.page_width + EPSILON:
        issues.append(
            LayoutIssue(
                "warning",
                "page_width_overflow",
                component.path,
                "Component extends beyond the page width.",
                {"component": component.label, "right": rect.right, "page_width": component.page_width},
            )
        )
    if component.page_height and rect.bottom > component.page_height + EPSILON:
        issues.append(
            LayoutIssue(
                "warning",
                "page_height_overflow",
                component.path,
                "Component extends beyond the page height.",
                {"component": component.label, "bottom": rect.bottom, "page_height": component.page_height},
            )
        )
    return issues


def find_overlaps(components: list[ComponentRef], *, overlap_tolerance: float) -> list[LayoutIssue]:
    issues: list[LayoutIssue] = []
    for index, left in enumerate(components):
        if left.rect is None:
            continue
        for right in components[index + 1 :]:
            if right.rect is None:
                continue
            if is_flow_band(left) and is_flow_band(right):
                continue
            intersection = left.rect.intersection_area(right.rect)
            if intersection <= EPSILON:
                continue
            smaller_area = min(left.rect.area, right.rect.area)
            if smaller_area <= EPSILON:
                continue
            ratio = intersection / smaller_area
            if ratio < overlap_tolerance:
                continue
            issues.append(
                LayoutIssue(
                    "warning",
                    "component_overlap",
                    left.parent_path,
                    "Visible components overlap in the same parent container.",
                    {
                        "components": [left.label, right.label],
                        "paths": [left.path, right.path],
                        "overlap_ratio": round(ratio, 4),
                    },
                )
            )
    return issues


def is_flow_band(component: ComponentRef) -> bool:
    return component.ident.startswith("Sti") and component.ident.endswith("Band")


def find_dynamic_height_risks(components: list[ComponentRef]) -> list[LayoutIssue]:
    issues: list[LayoutIssue] = []
    for growing in components:
        if growing.rect is None or not is_dynamic_height(growing.raw):
            continue
        for lower in components:
            if lower is growing or lower.rect is None:
                continue
            if lower.rect.top < growing.rect.bottom - EPSILON:
                continue
            if not growing.rect.horizontal_overlap(lower.rect):
                continue
            if has_shift_protection(lower.raw):
                continue
            issues.append(
                LayoutIssue(
                    "warning",
                    "dynamic_height_without_shift",
                    growing.path,
                    "A growing/shrinking component has a lower sibling without an explicit ShiftMode.",
                    {
                        "dynamic_component": growing.label,
                        "lower_component": lower.label,
                        "lower_path": lower.path,
                    },
                )
            )
    return issues


def find_mixed_row_growth(components: list[ComponentRef]) -> list[LayoutIssue]:
    issues: list[LayoutIssue] = []
    rows: dict[float, list[ComponentRef]] = {}
    for component in components:
        if component.rect is None:
            continue
        key = round(component.rect.top, 3)
        rows.setdefault(key, []).append(component)
    for top, row in rows.items():
        if len(row) < 2:
            continue
        dynamic_flags = {is_dynamic_height(component.raw) for component in row}
        if dynamic_flags == {True, False}:
            issues.append(
                LayoutIssue(
                    "warning",
                    "mixed_row_dynamic_height",
                    row[0].parent_path,
                    "Components on the same row mix dynamic and fixed height behavior.",
                    {
                        "top": top,
                        "components": [component.label for component in row],
                    },
                )
            )
    return issues


def parse_rect(component: dict[str, Any]) -> Rect | None:
    raw = component.get("ClientRectangle") or component.get("ClientRectangleD") or component.get("Rectangle")
    if isinstance(raw, str):
        parts = [parse_number(part.strip()) for part in raw.replace(";", ",").split(",")]
        if len(parts) >= 4 and all(part is not None for part in parts[:4]):
            return Rect(parts[0], parts[1], parts[2], parts[3])  # type: ignore[arg-type]
    if isinstance(raw, dict):
        left = parse_number(raw.get("Left") or raw.get("X"))
        top = parse_number(raw.get("Top") or raw.get("Y"))
        width = parse_number(raw.get("Width"))
        height = parse_number(raw.get("Height"))
        if None not in {left, top, width, height}:
            return Rect(left, top, width, height)  # type: ignore[arg-type]
    left = parse_number(component.get("Left"))
    top = parse_number(component.get("Top"))
    width = parse_number(component.get("Width"))
    height = parse_number(component.get("Height"))
    if None not in {left, top, width, height}:
        return Rect(left, top, width, height)  # type: ignore[arg-type]
    return None


def parse_number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


def iter_items(value: Any) -> list[tuple[str, Any]]:
    if isinstance(value, dict):
        return [(str(key), child) for key, child in value.items()]
    if isinstance(value, list):
        return [(str(index), child) for index, child in enumerate(value)]
    return []


def is_visible(component: dict[str, Any]) -> bool:
    return boolish(component.get("Enabled"), default=True) and boolish(component.get("Printable"), default=True)


def is_background_component(component: ComponentRef) -> bool:
    if component.ident in BACKGROUND_IDENTS:
        return True
    return "background" in component.name.lower()


def is_dynamic_height(component: dict[str, Any]) -> bool:
    return (
        boolish(component.get("CanGrow"), default=False)
        or boolish(component.get("CanShrink"), default=False)
        or boolish(component.get("GrowToHeight"), default=False)
    )


def has_shift_protection(component: dict[str, Any]) -> bool:
    value = component.get("ShiftMode")
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip().lower() not in {"", "none", "false", "0"}
    return bool(value)


def boolish(value: Any, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, int | float):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes"}:
            return True
        if lowered in {"false", "0", "no"}:
            return False
    return default


def count_by(items: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        value = str(item.get(key) or "")
        counts[value] = counts.get(value, 0) + 1
    return counts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate Stimulsoft report/dashboard JSON layout.")
    parser.add_argument("path", type=Path, help="Path to a .json/.mrt file or full Alterios report JSON.")
    parser.add_argument("--overlap-tolerance", type=float, default=0.05)
    parser.add_argument("--strict", action="store_true", help="Exit with code 1 on warnings as well as errors.")
    args = parser.parse_args(argv)

    payload = json.loads(args.path.read_text(encoding="utf-8"))
    result = analyze_stimulsoft_layout(payload, overlap_tolerance=args.overlap_tolerance)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if any(issue["severity"] == "error" for issue in result["issues"]):
        return 1
    if args.strict and result["issues"]:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
