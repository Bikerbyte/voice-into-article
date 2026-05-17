from __future__ import annotations

from pathlib import Path


def delete_file_if_exists(path: Path) -> bool:
    if not path.exists() or not path.is_file():
        return False
    path.unlink()
    return True
