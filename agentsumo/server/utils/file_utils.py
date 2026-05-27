"""
File handling utilities for SUMO MCP Server.
"""

import shutil
import datetime
from pathlib import Path
from typing import Optional, List


def copy_to_workdir(src: str, workdir: Path, zone_id: Optional[str] = None) -> str:
    """
    Copy file to working directory with optional zone prefix.
    
    Args:
        src: Source file path
        workdir: Working directory path
        zone_id: Optional zone ID for file naming
        
    Returns:
        str: Copied filename
        
    Raises:
        FileNotFoundError: If source file doesn't exist
    """
    if src is None:
        return None
        
    src_path = Path(src)
    dst_path = workdir / src_path.name
    
    # Check if source and destination are the same file
    if src_path.resolve() == dst_path.resolve():
        return src_path.name  # Return the filename without copying
    
    if not src_path.exists():
        raise FileNotFoundError(f"Input file not found: {src_path}")
    
    # Always copy (overwrite) for batch simulation compatibility
    shutil.copy2(src_path, dst_path)
    return dst_path.name


def copy_with_zone_prefix(src: str, workdir: Path, zone_id: str) -> str:
    """
    Copy file with zone prefix for batch simulation.
    
    Args:
        src: Source file path
        workdir: Working directory path
        zone_id: Zone ID for file naming
        
    Returns:
        str: Copied filename with zone prefix
        
    Raises:
        FileNotFoundError: If source file doesn't exist
    """
    if src is None:
        return None
        
    src_path = Path(src)
    # Add zone prefix to filename
    zone_filename = f"{zone_id}_{src_path.name}"
    dst_path = workdir / zone_filename
    
    if not src_path.exists():
        raise FileNotFoundError(f"Input file not found: {src_path}")
    
    # Check if source and destination are the same file
    if src_path.resolve() == dst_path.resolve():
        return zone_filename  # Return the filename without copying
    
    shutil.copy2(src_path, dst_path)
    return zone_filename


def ensure_directory(path: Path) -> Path:
    """
    Ensure directory exists, create if necessary.
    
    Args:
        path: Directory path
        
    Returns:
        Path: Directory path
    """
    path.mkdir(parents=True, exist_ok=True)
    return path


def copy_additional_files(additional_files: List[str], output_path: Path, zone_id: Optional[str] = None) -> List[str]:
    """
    Copy additional files to output directory.
    
    Args:
        additional_files: List of additional file paths
        output_path: Output directory path
        zone_id: Optional zone ID for file naming
        
    Returns:
        List[str]: List of copied filenames
    """
    copied_files = []
    
    for add_file_path in additional_files:
        if add_file_path:
            add_file_path_str = str(add_file_path)
            
            # Check if this is a zone-specific TLS file
            if zone_id and (f"{zone_id}_tls_offset" in add_file_path_str or f"{zone_id}_tls_adapt" in add_file_path_str):
                # Zone-specific TLS file - copy with zone prefix
                copied_name = copy_with_zone_prefix(add_file_path, output_path, zone_id)
            else:
                # Regular additional file
                copied_name = copy_to_workdir(add_file_path, output_path)
            
            if copied_name:
                copied_files.append(copied_name)
    
    return copied_files
