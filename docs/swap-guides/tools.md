# Swap guide: MCP tools (add your own)

The MCP surface is **pluggable** ([ADR 0012](../decisions/0012-mcp-tools-and-middleware.md)):
tools come from a registry (builtins + `afs.tools` entry points), and one
middleware applies **visibility**, **scope enforcement**, and **audit** to every
tool — builtin or third-party. So adding a tool makes the system more capable
without forking the mount, and your tool is a first-class citizen (enforced,
audited, claims-filtered) for free.

## The contract

```python
class Tool(Protocol):
    name: str                              # flat snake_case, unique
    required_scopes: frozenset[str]        # gates visibility + invocation
    required_capabilities: frozenset[str]  # reserved (namespace capabilities)
    def register(self, mcp: FastMCP, deps: ToolDeps) -> None: ...
```

`ToolDeps` hands you the shared, in-process services (`deps.fs`, `deps.settings`)
and `deps.resolve()` for the calling principal — the same service layer the REST
routes use, no HTTP self-calls. The docstring of the registered function **is**
the tool description the model sees; state the flow and the bounds.

## Write one

1. **Implement** the `Tool` protocol. In `register`, define a normal FastMCP tool
   function (typed params → input schema) that calls `deps`:
   ```python
   class FsHeadTool:
       name = "fs_head"
       required_scopes = frozenset({"fs:read"})
       required_capabilities = frozenset()

       def register(self, mcp, deps):
           @mcp.tool
           async def fs_head(namespace: str, path: str) -> dict:
               """First page of a document — a cheap peek before fs_read."""
               ctx = deps.resolve()
               result = await deps.fs.read(ctx, namespace, path, start_page=1, end_page=1)
               return result.model_dump(mode="json")
   ```
   You **don't** check scopes or log audit — the middleware does, from
   `required_scopes`. Declare them; don't enforce them.
2. **Register** it under the `afs.tools` entry-point group (a zero-arg factory):
   ```toml
   [project.entry-points."afs.tools"]
   fs_head = "mypkg.tools:FsHeadTool"
   ```
   (Or add it to `afs_server.tools.registry._BUILTIN_TOOLS` for a builtin.)

That's it. On the next mount the tool appears in `tools/list` for principals that
hold its scopes, is rejected for those that don't, and every call is audited.

Reference: `afs_server.tools` (`base` · `registry` · `middleware` · `builtin`).
