from __future__ import annotations

import importlib.resources as resources
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class NoteProfile:
    id: str
    name: str
    language: str
    category: str
    description: str
    tags: list[str]
    glossary: list[str]
    sections: list[str]
    corrections: dict[str, str]
    question_patterns: list[str]


def load_profile(profile: str | Path) -> NoteProfile:
    path = Path(profile)
    if path.exists():
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        return _profile_from_data(data)

    if not str(profile).endswith(".toml"):
        profile_name = f"{profile}.toml"
    else:
        profile_name = str(profile)

    try:
        profile_text = (
            resources.files("note_scribe")
            .joinpath("profiles")
            .joinpath(profile_name)
            .read_text(encoding="utf-8")
        )
    except FileNotFoundError as exc:
        raise ValueError(f"Unknown profile: {profile}") from exc

    return _profile_from_data(tomllib.loads(profile_text))


def list_builtin_profiles() -> list[str]:
    profile_dir = resources.files("note_scribe").joinpath("profiles")
    return sorted(item.name.removesuffix(".toml") for item in profile_dir.iterdir() if item.name.endswith(".toml"))


def _profile_from_data(data: dict[str, Any]) -> NoteProfile:
    return NoteProfile(
        id=str(data["id"]),
        name=str(data["name"]),
        language=str(data.get("language", "zh-TW")),
        category=str(data.get("category", "general")),
        description=str(data.get("description", "")),
        tags=[str(item) for item in data.get("tags", [])],
        glossary=[str(item) for item in data.get("glossary", [])],
        sections=[str(item) for item in data.get("sections", [])],
        corrections={str(k): str(v) for k, v in data.get("corrections", {}).items()},
        question_patterns=[str(item) for item in data.get("question_patterns", [])],
    )
