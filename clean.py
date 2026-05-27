#!/usr/bin/env python3
"""
AgentSUMO Output Cleaner

output 폴더 내 파일들을 정리.
vehicle_types.add.xml은 보존.
"""

import shutil
from pathlib import Path

# 프로젝트 루트
PROJECT_ROOT = Path(__file__).parent
OUTPUT_DIR = PROJECT_ROOT / "agentsumo" / "output"

# 보존할 파일들
PRESERVE_FILES = {
    "vehicle_types.add.xml",
}

# 정리할 하위 폴더들
CLEAN_FOLDERS = [
    "networks",
    "trips",
    "simulations",
    "analysis",
    "reports",
    "visualizations",
]


def clean_output():
    """output 폴더 정리"""
    if not OUTPUT_DIR.exists():
        print("output 폴더가 없습니다.")
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
                print(f"  보존: {folder_name}/{file.name}")
            elif file.is_file():
                file.unlink()
                deleted_count += 1
            elif file.is_dir():
                shutil.rmtree(file)
                deleted_count += 1

    print(f"\n정리 완료: {deleted_count}개 삭제, {preserved_count}개 보존")


if __name__ == "__main__":
    print("AgentSUMO Output Cleaner")
    print("=" * 40)
    print(f"대상: {OUTPUT_DIR}")
    print()

    response = input("output 폴더를 정리할까요? (y/N): ").strip().lower()
    if response == "y":
        clean_output()
    else:
        print("취소되었습니다.")
