"""
Path handling utilities for SUMO MCP Server.
"""

from pathlib import Path
from typing import Optional


def get_output_path(output_dir: str, base_dir: Optional[Path] = None) -> Path:
    """
    Get output directory path, creating if necessary.
    
    IMPORTANT: All output paths are relative to agentsumo/ directory, not project root.
    This ensures MCP server outputs are contained within the agentsumo package.
    
    Args:
        output_dir: Output directory path (e.g., "output/analysis")
        base_dir: Base directory for relative paths (defaults to agentsumo/)
        
    Returns:
        Path: Output directory path (e.g., /path/to/agentsumo/output/analysis)
    """
    if base_dir is None:
        # Default to agentsumo/ directory
        # path_utils.py 위치: agentsumo/server/utils/path_utils.py
        # .parent → utils/, .parent.parent → server/, .parent.parent.parent → agentsumo/
        base_dir = Path(__file__).parent.parent.parent
    
    if Path(output_dir).is_absolute():
        output_path = Path(output_dir)
    else:
        output_path = base_dir / output_dir
    
    output_path.mkdir(parents=True, exist_ok=True)
    return output_path


def get_working_directory() -> Path:
    """
    Get the working directory (agentsumo/ directory).
    
    IMPORTANT: Returns agentsumo/ directory to keep all MCP server outputs
    contained within the package, not scattered in project root.
    
    Returns:
        Path: Working directory path (agentsumo/)
    """
    # path_utils.py 위치: agentsumo/server/utils/path_utils.py
    # .parent → utils/, .parent.parent → server/, .parent.parent.parent → agentsumo/
    return Path(__file__).parent.parent.parent


