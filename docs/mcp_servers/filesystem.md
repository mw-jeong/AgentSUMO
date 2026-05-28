# Filesystem MCP Server

The Filesystem MCP server is **maintained by Anthropic**. It provides
primitive file-system tools (read, write, list, search) that the Planner
Agent uses to handle user uploads, write supplementary SUMO configuration
files, and inspect generated artifacts.

## Official documentation

::::{grid} 1
:gutter: 2

:::{grid-item-card} modelcontextprotocol/servers — Filesystem
:link: https://github.com/modelcontextprotocol/servers/tree/main/src/filesystem
:class-card: sd-text-center

`github.com/modelcontextprotocol/servers/tree/main/src/filesystem`
:::

::::

## Tools used by AgentSUMO

| Tool | Purpose |
|---|---|
| `read_file` | Read file contents (user uploads, generated XML). |
| `write_file` | Write supplementary SUMO XML configurations. |
| `read_multiple_files` | Batch-read several files in one call. |
| `list_directory` | Inspect the contents of an output folder. |
| `search_files` | Find files by pattern (e.g., locate the latest `tripinfo.xml`). |
| `get_file_info` | Retrieve file metadata. |
| `create_directory` | Create new output subdirectories on demand. |

## How AgentSUMO uses it

The Filesystem MCP server is launched at AgentSUMO startup with read/write
access restricted to the project working directory: the `output/` tree, the
`agentsumo/agent/additional_files_guide/` markdown guides, and any
user-supplied data files explicitly placed in the project tree.

Three concrete patterns:

1. **Reading user uploads.** When a user provides an OD matrix as a CSV file,
   the Planner Agent reads it via `read_file` to verify column structure and
   coordinate format before passing the path to `trip_generate`.
2. **Writing supplementary XML configurations.** Many SUMO policy
   interventions are temporal or conditional (e.g., time-based road
   closures, variable speed limits, fleet composition changes). These are
   implemented through supplementary XML files loaded alongside the network
   at simulation time. The agent writes these files via `write_file`,
   guided by three markdown guides bundled with AgentSUMO (`rerouter.md`,
   `variable_speed_sign.md`, `vtype.md`). The generated files are passed to
   `sumo_runner` through its `additional_files` parameter.
3. **Inspecting generated artifacts.** After tool execution, the agent uses
   `list_directory` and `read_file` to verify output and diagnose errors
   before reporting back to the user.
