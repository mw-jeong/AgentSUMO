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

The server exposes thirteen tools across three categories, matching the
layout in Figure 3 of the paper.

| Category | Tool | Purpose |
|---|---|---|
| **Read** | `read_text_file` | Read a text file's contents. |
| **Read** | `read_media_file` | Read a binary media file (returns base64). |
| **Read** | `read_multiple_files` | Batch-read several files in one call. |
| **Read** | `list_directory` | List the entries of a directory. |
| **Read** | `list_directory_with_sizes` | List entries together with file sizes. |
| **Read** | `directory_tree` | Recursive JSON tree of a directory. |
| **Read** | `search_files` | Find files by name pattern. |
| **Read** | `get_file_info` | Retrieve file metadata (size, mtime, permissions). |
| **Read** | `list_allowed_directories` | List the directories the server is configured to access. |
| **Write** | `write_file` | Write or overwrite a file. |
| **Write** | `edit_file` | Apply line-based edits to an existing file. |
| **Write** | `create_directory` | Create a directory (idempotent). |
| **Manage** | `move_file` | Move or rename a file. |

## How AgentSUMO uses it

The Filesystem MCP server is launched at AgentSUMO startup with access
restricted to the project working directory: the `output/` tree, the
`agentsumo/agent/additional_files_guide/` markdown guides, and any
user-supplied data files explicitly placed in the project tree.

Three concrete patterns:

1. **Reading user uploads.** When a user provides an OD matrix as a CSV
   file, the Planner Agent reads it via `read_text_file` to verify column
   structure and coordinate format before passing the path to
   `trip_generate`.
2. **Writing supplementary XML configurations.** Many SUMO policy
   interventions are temporal or conditional (e.g., time-based road
   closures, variable speed limits, fleet composition changes). These are
   implemented through supplementary XML files loaded alongside the network
   at simulation time. The agent writes these files via `write_file`,
   guided by three markdown guides bundled with AgentSUMO (`rerouter.md`,
   `vss.md`, `vtype.md`). The generated files are passed to
   `sumo_runner` through its `additional_files` parameter.
3. **Inspecting generated artifacts.** After tool execution, the agent uses
   `list_directory` and `read_text_file` to verify output and diagnose
   errors before reporting back to the user.
