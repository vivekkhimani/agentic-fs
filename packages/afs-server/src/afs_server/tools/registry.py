"""The tool registry (ADR 0012) — builtins + ``afs.tools`` plugins.

Adding a tool is implement + register, never fork the MCP mount: ship a class
that satisfies the ``Tool`` protocol and expose it under the ``afs.tools`` entry
point group (or add it to ``_BUILTIN_TOOLS``). Resolved by name like the store /
normalizer registries (ADR 0002, pluggable backends via entry points).
"""

from __future__ import annotations

from importlib.metadata import entry_points

from afs_server.tools.base import Tool
from afs_server.tools.builtin import (
    FsDiffTool,
    FsFindTool,
    FsGlobTool,
    FsGrepTool,
    FsListTool,
    FsOutlineTool,
    FsReadTool,
    FsStatTool,
    FsTablesTool,
    FsTreeTool,
    ScratchDeleteTool,
    ScratchListTool,
    ScratchReadTool,
    ScratchWriteTool,
    WhoamiTool,
)

_TOOL_ENTRY_GROUP = "afs.tools"

# Builtin tools: name -> factory (zero-arg). Always available.
_BUILTIN_TOOLS: dict[str, type[Tool]] = {
    cls.name: cls
    for cls in (
        WhoamiTool,
        FsListTool,
        FsStatTool,
        FsReadTool,
        FsGlobTool,
        FsGrepTool,
        FsTreeTool,
        FsFindTool,
        FsOutlineTool,
        FsTablesTool,
        FsDiffTool,
        ScratchWriteTool,
        ScratchReadTool,
        ScratchListTool,
        ScratchDeleteTool,
    )
}


def build_tools() -> list[Tool]:
    """All mounted tools: the builtins plus every registered ``afs.tools`` plugin."""
    tools: list[Tool] = [cls() for cls in _BUILTIN_TOOLS.values()]
    seen = set(_BUILTIN_TOOLS)
    for ep in entry_points(group=_TOOL_ENTRY_GROUP):
        tool = ep.load()()
        if tool.name in seen:
            raise ValueError(f"duplicate tool name {tool.name!r} from plugin {ep.name!r}")
        seen.add(tool.name)
        tools.append(tool)
    return tools
