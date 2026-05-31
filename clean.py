#!/usr/bin/env python3
"""
AgentSUMO Output Cleaner

Cleans files inside the output folder.
vehicle_types.add.xml is preserved.
"""

import shutil
from pathlib import Path

# Project root
PROJECT_ROOT = Path(__file__).parent
OUTPUT_DIR = PROJECT_ROOT / "agentsumo" / "output"

# Files to preserve
PRESERVE_FILES = {
    "vehicle_types.add.xml",
}

# Subfolders to clean
CLEAN_FOLDERS = [
    "networks",
    "trips",
    "simulations",
    "analysis",
    "reports",
    "visualizations",
]


def clean_output():
    """Clean the output folder."""
    if not OUTPUT_DIR.exists():
        print("Output folder does not exist.")
        return

    deleted_count = 0
    preserved_count = 0

    for folder_name in CLEAN_FOLDERS:
        folder = OUTPUT_DIR / folder_name
        if not folder.exists():
            continue

        for file in folder.iterdir():
            if file.name in PRESERVE_FILES:
                preserved_count += 1
                print(f"  Preserved {folder_name}/{file.name}")
            elif file.is_file():
                file.unlink()
                deleted_count += 1
            elif file.is_dir():
                shutil.rmtree(file)
                deleted_count += 1

    print(f"\nCleanup complete. {deleted_count} deleted, {preserved_count} preserved.")


if __name__ == "__main__":
    print("AgentSUMO Output Cleaner")
    print("=" * 40)
    print(f"Target: {OUTPUT_DIR}")
    print()

    response = input("Clean the output folder? (y/N): ").strip().lower()
    if response == "y":
        clean_output()
    else:
        print("Cancelled.")
