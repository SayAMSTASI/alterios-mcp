"""Domain registration modules for the Alterios MCP surface."""

from __future__ import annotations

from typing import Any, Callable

from . import runtime
from . import workboard
from . import write_audit
from . import discovery
from . import icons
from . import security
from . import content
from . import views_forms
from . import processes
from . import reports
from . import live
from . import diagnostics


DOMAIN_MODULES = (
    runtime,
    workboard,
    write_audit,
    discovery,
    icons,
    security,
    content,
    views_forms,
    processes,
    reports,
    live,
    diagnostics,
)


def all_tool_functions() -> tuple[Callable[..., Any], ...]:
    functions = tuple(tool for module in DOMAIN_MODULES for tool in module.tool_functions())
    names = [tool.__name__ for tool in functions]
    if len(names) != len(set(names)):
        raise RuntimeError("Duplicate MCP tool names were found in domain registrations.")
    return functions


def all_tool_names() -> list[str]:
    return [tool.__name__ for tool in all_tool_functions()]


def register_all_tools(mcp: Any) -> tuple[str, ...]:
    registered = tuple(name for module in DOMAIN_MODULES for name in module.register(mcp))
    if len(registered) != len(set(registered)):
        raise RuntimeError("Duplicate MCP tool names were registered.")
    return registered
