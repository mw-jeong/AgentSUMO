"""
Path handling utilities for SUMO MCP Server.
"""

import os
from pathlib import Path
from typing import Optional


_ENV_BASE_DIR = "AGENTSUMO_MCP_OUTPUT_BASE"


def _resolve_base_dir() -> Path:
    """Resolve the base directory for relative output paths.

    Order of precedence:
      1. AGENTSUMO_MCP_OUTPUT_BASE environment variable.
      2. Current working directory.
    """
    env_dir = os.environ.get(_ENV_BASE_DIR)
    if env_dir:
        return Path(env_dir).expanduser()
    return Path.cwd()


def get_output_path(output_dir: str, base_dir: Optional[Path] = None) -> Path:
    """
    Resolve and create an output directory.

    Absolute paths are used as-is. Relative paths are joined with `base_dir`
    if explicitly provided, otherwise with the value returned by
    `_resolve_base_dir()` (env var > CWD).

    Args:
        output_dir: Output directory path (absolute or relative, e.g.
            "output/analysis").
        base_dir: Explicit base directory for relative paths. If omitted,
            falls back to the AGENTSUMO_MCP_OUTPUT_BASE env var, then CWD.

    Returns:
        Path: The resolved (and now-existing) output directory.
    """
    if Path(output_dir).is_absolute():
        output_path = Path(output_dir)
    else:
        root = base_dir if base_dir is not None else _resolve_base_dir()
        output_path = root / output_dir

    output_path.mkdir(parents=True, exist_ok=True)
    return output_path


def get_working_directory() -> Path:
    """
    Return the base directory used for MCP server outputs.

    Honors AGENTSUMO_MCP_OUTPUT_BASE if set, otherwise returns the current
    working directory.
    """
    return _resolve_base_dir()
