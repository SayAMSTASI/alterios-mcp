from __future__ import annotations

from functools import wraps
from typing import Any, Callable

from mcp.server.fastmcp import FastMCP

from . import _support
from ._support import *
from .scenarios import runtime as _runtime_scenarios
from .scenarios import workboard as _workboard_scenarios
from .scenarios import write_audit as _write_audit_scenarios
from .scenarios import discovery as _discovery_scenarios
from .scenarios import icons as _icons_scenarios
from .scenarios import security as _security_scenarios
from .scenarios import content as _content_scenarios
from .scenarios import views_forms as _views_forms_scenarios
from .scenarios import processes as _processes_scenarios
from .scenarios import reports as _reports_scenarios
from .scenarios import live as _live_scenarios
from .scenarios import diagnostics as _diagnostics_scenarios
from .tool_profiles import apply_tool_profile
from .tools import all_tool_functions, all_tool_names, register_all_tools


mcp = FastMCP("alterios")
register_all_tools(mcp)
_support.configure_tool_name_provider(all_tool_names)

_SCENARIO_MODULES = (
    _runtime_scenarios,
    _workboard_scenarios,
    _write_audit_scenarios,
    _discovery_scenarios,
    _icons_scenarios,
    _security_scenarios,
    _content_scenarios,
    _views_forms_scenarios,
    _processes_scenarios,
    _reports_scenarios,
    _live_scenarios,
    _diagnostics_scenarios,
)
_PATCHABLE_COMPAT_BINDINGS = (
    "AlteriosClient",
    "GiteaClient",
    "_assert_delivery_evidence",
    "_assert_runtime_gate",
    "_client",
    "_download_google_icon_svg",
    "_verify_delivery_evidence",
    "run_live_task_preflight",
)


def _sync_compat_bindings() -> None:
    for name in _PATCHABLE_COMPAT_BINDINGS:
        if name not in globals():
            continue
        value = globals()[name]
        if hasattr(_support, name):
            setattr(_support, name, value)
        for module in _SCENARIO_MODULES:
            if hasattr(module, name):
                setattr(module, name, value)


def _compat_wrapper(function: Callable[..., Any]) -> Callable[..., Any]:
    @wraps(function)
    def invoke(*args: Any, **kwargs: Any) -> Any:
        _sync_compat_bindings()
        return function(*args, **kwargs)

    return invoke


for _name in _support.__all__:
    globals().setdefault(_name, getattr(_support, _name))
for _function in all_tool_functions():
    globals()[_function.__name__] = _compat_wrapper(_function)


def _decorated_tool_names() -> list[str]:
    return all_tool_names()


def _activate_tool_profile() -> dict[str, Any]:
    profile = apply_tool_profile(mcp, all_tool_names())
    _support.set_active_tool_profile(profile)
    globals()["_ACTIVE_TOOL_PROFILE"] = profile
    return profile


_activate_tool_profile()


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
