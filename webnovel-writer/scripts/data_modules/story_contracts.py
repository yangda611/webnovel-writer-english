#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List

from chapter_outline_loader import volume_num_for_chapter_from_state

try:
    from security_utils import atomic_write_json
except ImportError:  # pragma: no cover
    from scripts.security_utils import atomic_write_json


MARKER_BEGIN = "<!-- STORY-SYSTEM:BEGIN -->"
MARKER_END = "<!-- STORY-SYSTEM:END -->"


@dataclass(frozen=True)
class StoryContractPaths:
    project_root: Path

    @classmethod
    def from_project_root(cls, project_root: str | Path) -> "StoryContractPaths":
        return cls(Path(project_root).expanduser().resolve())

    @property
    def root(self) -> Path:
        return self.project_root / ".story-system"

    @property
    def chapters_dir(self) -> Path:
        return self.root / "chapters"

    @property
    def volumes_dir(self) -> Path:
        return self.root / "volumes"

    @property
    def reviews_dir(self) -> Path:
        return self.root / "reviews"

    @property
    def commits_dir(self) -> Path:
        return self.root / "commits"

    @property
    def events_dir(self) -> Path:
        return self.root / "events"

    @property
    def master_json(self) -> Path:
        return self.root / "MASTER_SETTING.json"

    @property
    def anti_patterns_json(self) -> Path:
        return self.root / "anti_patterns.json"

    def chapter_json(self, chapter: int) -> Path:
        return self.chapters_dir / f"chapter_{chapter:03d}.json"

    def volume_json(self, volume: int) -> Path:
        return self.volumes_dir / f"volume_{volume:03d}.json"

    def review_json(self, chapter: int) -> Path:
        return self.reviews_dir / f"chapter_{chapter:03d}.review.json"

    def commit_json(self, chapter: int) -> Path:
        return self.commits_dir / f"chapter_{chapter:03d}.commit.json"

    def event_json(self, chapter: int) -> Path:
        return self.events_dir / f"chapter_{chapter:03d}.events.json"


def _merge_append_only(master: Dict[str, Any], chapter: Dict[str, Any]) -> Dict[str, List[Any]]:
    merged: Dict[str, List[Any]] = {}
    for key in set(master) | set(chapter):
        seen: List[Any] = []
        for source_list in (master.get(key) or [], chapter.get(key) or []):
            for item in source_list:
                if item not in seen:
                    seen.append(item)
        merged[key] = seen
    return merged


def merge_contract_layers(master: Dict[str, Any], chapter: Dict[str, Any] | None) -> Dict[str, Any]:
    chapter = chapter or {}
    return {
        "locked": dict(master.get("locked") or {}),
        "append_only": _merge_append_only(
            master.get("append_only") or {},
            chapter.get("append_only") or {},
        ),
        "override_allowed": {
            **(master.get("override_allowed") or {}),
            **(chapter.get("override_allowed") or {}),
        },
    }


def merge_anti_patterns(*groups: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen: set[str] = set()
    merged: List[Dict[str, Any]] = []
    for group in groups:
        for row in group:
            text = str(row.get("text") or "").strip()
            if not text or text in seen:
                continue
            seen.add(text)
            merged.append(dict(row))
    return merged


def read_json_if_exists(path: Path) -> Any | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Bad JSON in {path}") from exc


def write_json(path: Path, payload: Any) -> None:
    atomic_write_json(path, payload, backup=True)


def write_marked_markdown(path: Path, generated_block: str) -> None:
    wrapped = f"{MARKER_BEGIN}\n{generated_block.rstrip()}\n{MARKER_END}\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        current = path.read_text(encoding="utf-8")
        if current.count(MARKER_BEGIN) > 1 or current.count(MARKER_END) > 1:
            raise ValueError(f"{path} contains multiple STORY-SYSTEM markers")
        if current.count(MARKER_BEGIN) != current.count(MARKER_END):
            raise ValueError(f"{path} contains incomplete STORY-SYSTEM markers")
        if MARKER_BEGIN in current and MARKER_END in current:
            if current.index(MARKER_END) < current.index(MARKER_BEGIN):
                raise ValueError(f"{path} contains reversed STORY-SYSTEM markers")
            before, _, rest = current.partition(MARKER_BEGIN)
            _, _, after = rest.partition(MARKER_END)
            path.write_text(f"{before}{wrapped}{after.lstrip()}", encoding="utf-8")
            return
        path.write_text(f"{current.rstrip()}\n\n{wrapped}", encoding="utf-8")
        return
    path.write_text(wrapped, encoding="utf-8")


def render_master_markdown(master_payload: Dict[str, Any]) -> str:
    route = master_payload.get("route") or {}
    constraints = master_payload.get("master_constraints") or {}
    return "\n".join(
        [
            "# MASTER_SETTING",
            f"- 题材：{route.get('primary_genre', '')}",
            f"- 调性：{constraints.get('core_tone', '')}",
            f"- 节奏：{constraints.get('pacing_strategy', '')}",
        ]
    )


def render_anti_patterns_markdown(anti_patterns: List[Dict[str, Any]]) -> str:
    lines = ["# ANTI_PATTERNS"]
    for row in anti_patterns:
        lines.append(f"- {row.get('text', '')}")
    return "\n".join(lines)


def render_chapter_markdown(chapter_payload: Dict[str, Any]) -> str:
    focus = (chapter_payload.get("override_allowed") or {}).get("chapter_focus", "")
    return "\n".join(
        [
            f"# CHAPTER_{int(chapter_payload['meta']['chapter']):03d}",
            f"- 章节焦点：{focus}",
        ]
    )


def _override_object(payload: Dict[str, Any], field: str, path: Path) -> Dict[str, Any]:
    value = payload.get(field, {})
    if not isinstance(value, dict):
        raise ValueError(f"{path}: {field} must be an object; refusing to discard author constraints")
    return value


def _preserve_child_overrides(path: Path, generated: Dict[str, Any], *, chapter: bool = False) -> Dict[str, Any]:
    """Refresh generated fields while retaining only documented editable containers.

    Existing editable values take precedence because generated and author-edited
    values have no separate provenance. Locked collisions require an explicit
    resolution; append-only values retain order and de-duplicate.
    """
    existing = read_json_if_exists(path)
    if existing is None:
        return generated
    if not isinstance(existing, dict):
        raise ValueError(f"{path}: existing contract must be an object")
    old_meta = _override_object(existing, "meta", path)
    new_meta = _override_object(generated, "meta", path)
    old_ref = _override_object(old_meta, "writing_profile_ref", path)
    new_ref = _override_object(new_meta, "writing_profile_ref", path)
    explicit = any(ref and not ref.get("legacy") for ref in (old_ref, new_ref))
    if explicit and any(old_meta.get(key) != new_meta.get(key) for key in (
        "writing_profile_ref", "rule_pack_versions", "language_pack_version",
    )):
        raise ValueError(f"{path}: writing profile reference/version conflict; explicit migration is required")
    if chapter:
        return {**generated, "override_allowed": {
            **_override_object(generated, "override_allowed", path),
            **_override_object(existing, "override_allowed", path),
        }}
    old_bundle = _override_object(existing, "overrides", path)
    new_bundle = _override_object(generated, "overrides", path)
    old_locked = _override_object(old_bundle, "locked", path)
    new_locked = _override_object(new_bundle, "locked", path)
    for key in old_locked.keys() & new_locked.keys():
        if old_locked[key] != new_locked[key]:
            raise ValueError(f"{path}: locked author override conflict for {key}")
    old_append = _override_object(old_bundle, "append_only", path)
    new_append = _override_object(new_bundle, "append_only", path)
    if any(not isinstance(value, list) for bundle in (old_append, new_append) for value in bundle.values()):
        raise ValueError(f"{path}: append_only values must be lists; refusing to discard author constraints")
    return {**generated, "overrides": {
        "locked": {**new_locked, **old_locked},
        "append_only": _merge_append_only(old_append, new_append),
        "override_allowed": {
            **_override_object(new_bundle, "override_allowed", path),
            **_override_object(old_bundle, "override_allowed", path),
        },
    }}


def persist_story_seed(
    project_root: Path,
    master_payload: Dict[str, Any],
    chapter_payload: Dict[str, Any] | None,
    anti_patterns: List[Dict[str, Any]],
) -> None:
    paths = StoryContractPaths.from_project_root(project_root)
    existing = read_json_if_exists(paths.master_json) or {}
    if existing:
        old_meta = existing.get("meta") or {}
        new_meta = master_payload.get("meta") or {}
        old_ref = old_meta.get("writing_profile_ref") or {}
        new_ref = new_meta.get("writing_profile_ref") or {}
        if old_ref and not old_ref.get("legacy") and old_ref != new_ref:
            raise ValueError("MASTER_SETTING writing profile reference conflicts; explicit migration is required")
        # Refresh generated context while retaining initialization choices and
        # author-added data. The persisted profile remains the authority.
        new_constraints = master_payload.get("master_constraints") or {}
        existing_constraints = existing.get("master_constraints") or {}
        merged_constraints = {**new_constraints, **existing_constraints}
        if "writing_profile" in new_constraints:
            merged_constraints["writing_profile"] = new_constraints["writing_profile"]
        master_payload = {
            **existing,
            **master_payload,
            "meta": {**old_meta, **new_meta},
            "master_constraints": merged_constraints,
            "route": {**(existing.get("route") or {}), **(master_payload.get("route") or {})},
        }
    anti_patterns = merge_anti_patterns(read_json_if_exists(paths.anti_patterns_json) or [], anti_patterns)
    if chapter_payload is not None:
        chapter_num = int(chapter_payload["meta"]["chapter"])
        chapter_payload = _preserve_child_overrides(paths.chapter_json(chapter_num), chapter_payload, chapter=True)
    paths.root.mkdir(parents=True, exist_ok=True)
    paths.chapters_dir.mkdir(parents=True, exist_ok=True)
    write_json(paths.master_json, master_payload)
    write_json(paths.anti_patterns_json, anti_patterns)
    write_marked_markdown(paths.master_json.with_suffix(".md"), render_master_markdown(master_payload))
    write_marked_markdown(
        paths.anti_patterns_json.with_suffix(".md"),
        render_anti_patterns_markdown(anti_patterns),
    )
    if chapter_payload is not None:
        chapter_num = int(chapter_payload["meta"]["chapter"])
        write_json(paths.chapter_json(chapter_num), chapter_payload)
        write_marked_markdown(
            paths.chapter_json(chapter_num).with_suffix(".md"),
            render_chapter_markdown(chapter_payload),
        )


def persist_runtime_contracts(
    project_root: Path,
    chapter: int,
    volume_brief: Dict[str, Any],
    review_contract: Dict[str, Any],
) -> None:
    paths = StoryContractPaths.from_project_root(project_root)
    volume = volume_num_for_chapter_from_state(paths.project_root, chapter) or 1
    # Validate both refreshes before writing either file, so a conflict cannot
    # leave the volume and review carrying different generations of constraints.
    volume_brief = _preserve_child_overrides(paths.volume_json(volume), volume_brief)
    review_contract = _preserve_child_overrides(paths.review_json(chapter), review_contract)
    paths.volumes_dir.mkdir(parents=True, exist_ok=True)
    paths.reviews_dir.mkdir(parents=True, exist_ok=True)
    write_json(paths.volume_json(volume), volume_brief)
    write_json(paths.review_json(chapter), review_contract)
