"""Generate the public tool/profile matrix from the executable registry."""
from __future__ import annotations

import argparse
from pathlib import Path

from . import __version__
from .tool_profiles import TOOL_PROFILES, allowed_tool_names, classify_tool
from .tools import all_tool_functions


def render_capabilities() -> str:
    functions = sorted(all_tool_functions(), key=lambda item: item.__name__)
    names = [tool.__name__ for tool in functions]
    enabled = {profile: set(allowed_tool_names(names, profile)) for profile in TOOL_PROFILES}
    lines = ["# Каталог инструментов MCP", "", f"Версия пакета: `{__version__}`.", "",
             "Сгенерировано командой `python -m alterios_mcp.capabilities`. Не редактировать вручную.", "",
             "Этот каталог подтверждает регистрацию инструментов и доступность в профилях; он не подтверждает проверку на живом контуре.", "",
             "| Профиль | Инструментов |", "|---|---:|"]
    lines += [f"| {profile} | {len(enabled[profile])} |" for profile in TOOL_PROFILES]
    lines += ["", "| Инструмент | Класс | full | live | discovery | admin |", "|---|---|---|---|---|---|"]
    for tool in functions:
        name = tool.__name__
        flags = " | ".join("да" if name in enabled[p] else "—" for p in TOOL_PROFILES)
        lines.append(f"| `{name}` | {classify_tool(name)} | {flags} |")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("docs/capabilities.md"))
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    expected = render_capabilities()
    if args.check:
        if not args.output.exists() or args.output.read_text(encoding="utf-8") != expected:
            print("Capability catalog is stale; regenerate it.")
            return 1
        print("Capability catalog matches the executable registry.")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(expected, encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
