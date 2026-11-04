"""Authoritative per-project market, prose language and writing rules.

Only projects without *any* new configuration markers receive legacy defaults.
Display snapshots never override a persisted profile or repair a damaged one.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Literal

from filelock import FileLock
from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, model_validator

from security_utils import atomic_write_json
from .rule_registry import DOMESTIC_RULE_VERSION, genre_versions, read_pack, resolve_genres

PROFILE_PATH = ".story-system/WRITING_PROFILE.json"


class WritingProfileError(ValueError):
    pass


class WritingProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    schema_version: Literal[1] = 1
    market: Literal["domestic", "overseas"] = "domestic"
    body_language: Literal["zh", "en"] = "zh"
    primary_genre: str = Field(min_length=1)
    secondary_genres: list[str] = Field(default_factory=list)
    chapter_length: int = Field(gt=0)
    chapter_unit: Literal["characters", "words"]
    rule_pack_versions: dict[str, str]
    language_pack_version: str = Field(min_length=1)
    pov: str | None = None
    tense: str | None = None
    platform: str | None = None
    allow_draft_rules: bool = False
    _legacy: bool = PrivateAttr(default=False)

    @model_validator(mode="after")
    def check_consistency(self) -> WritingProfile:
        if self.market == "domestic" and self.body_language != "zh":
            raise ValueError("第一版国内市场仅支持中文正文")
        if self.chapter_unit != ("words" if self.body_language == "en" else "characters"):
            raise ValueError("章长单位必须与正文语言一致：中文 characters，英文 words")
        genres = [self.primary_genre, *self.secondary_genres]
        if any(not value.strip() for value in genres) or len(set(genres)) != len(genres):
            raise ValueError("主辅题材不能为空或重复")
        expected = set(genres) if self.market == "overseas" else {"domestic-legacy"}
        if set(self.rule_pack_versions) != expected:
            raise ValueError("规则包版本必须完整覆盖所选主辅题材，且不得混入其他市场")
        return self

    def to_snapshot(self) -> dict[str, Any]:
        return self.model_dump(mode="json")

    def reference(self) -> dict[str, Any]:
        encoded = json.dumps(self.to_snapshot(), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return {"path": PROFILE_PATH, "sha256": hashlib.sha256(encoded).hexdigest(),
                "schema_version": self.schema_version, "legacy": self._legacy,
                "rule_pack_versions": dict(self.rule_pack_versions),
                "language_pack_version": self.language_pack_version}


def build_writing_profile(*, market: str = "domestic", body_language: str = "zh", genre: str,
                          secondary_genres: list[str] | None = None, chapter_length: int | None = None,
                          chapter_unit: str | None = None, pov: str | None = None,
                          tense: str | None = None, platform: str | None = None,
                          allow_draft_rules: bool = False,
                          rule_pack_versions: dict[str, str] | None = None,
                          language_pack_version: str | None = None) -> WritingProfile:
    if market not in {"domestic", "overseas"}:
        raise WritingProfileError(f"未知市场：{market}")
    genres = resolve_genres(genre, secondary_genres, market)
    profile = WritingProfile(
        market=market, body_language=body_language, primary_genre=genres[0], secondary_genres=genres[1:],
        chapter_length=chapter_length if chapter_length is not None else (2000 if body_language == "en" else 3000),
        chapter_unit=chapter_unit or ("words" if body_language == "en" else "characters"),
        rule_pack_versions=rule_pack_versions if rule_pack_versions is not None else genre_versions(genres, market),
        language_pack_version=language_pack_version if language_pack_version is not None else read_pack("languages", body_language)["version"],
        pov=pov or None, tense=tense or None, platform=platform or None, allow_draft_rules=allow_draft_rules,
    )
    load_rule_bundles(profile)
    return profile


def load_rule_bundles(profile: WritingProfile) -> dict[str, Any]:
    language = read_pack("languages", profile.body_language, profile.language_pack_version)
    if profile.market == "overseas":
        rules = [read_pack("genres", key, profile.rule_pack_versions[key])
                 for key in [profile.primary_genre, *profile.secondary_genres]]
        if not profile.allow_draft_rules and any(pack["status"] == "draft" for pack in rules):
            raise WritingProfileError("国外规则包为 draft；仅可显式 allow_draft_rules/--allow-draft-rules 试用，尚未正式支持")
    else:
        if profile.rule_pack_versions != {"domestic-legacy": DOMESTIC_RULE_VERSION}:
            raise WritingProfileError("国内规则包版本不匹配")
        if not profile._legacy:
            # Validate persisted identifiers too, not only constructor inputs.
            genres = [profile.primary_genre, *profile.secondary_genres]
            if resolve_genres(profile.primary_genre, profile.secondary_genres, "domestic") != genres:
                raise WritingProfileError("国内题材标识必须与注册名称一致")
        rules = [{"id": "domestic-legacy", "version": DOMESTIC_RULE_VERSION, "market": "domestic",
                  "status": "verified", "genres": [profile.primary_genre, *profile.secondary_genres],
                  "scope": "旧国内模板与 CSV，仅供国内项目；不代表经过海外读者验证"}]
    return {"genre_rules": rules, "language_rules": language}


def _has_markers(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    reference = payload.get("writing_profile_ref")
    if reference and not (isinstance(reference, dict) and reference.get("legacy") is True):
        return True
    if any(payload.get(key) for key in ("writing_profile", "rule_pack_versions", "body_language", "market")):
        return True
    # Only configuration containers establish an explicit project selection.
    # Chapter measurements also carry body_language, and a legacy reference may
    # be displayed without creating an authoritative configuration file.
    return any(_has_markers(payload.get(key)) for key in
               ("project_info", "project", "meta", "route", "master_constraints"))


def _read_marker_source(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    text = ""
    try:
        text = path.read_text(encoding="utf-8")
        payload = json.loads(text)
        if not isinstance(payload, dict):
            raise WritingProfileError(f"配置来源不是对象：{path}")
        return payload
    except (OSError, ValueError) as exc:
        # Old init can preserve and recover a corrupt legacy state. A source
        # containing any new marker must never become an implicit domestic book.
        if path.name != "state.json" or any(f'"{key}"' in text
                                               for key in ("market", "body_language", "writing_profile", "writing_profile_ref", "rule_pack_versions")):
            raise WritingProfileError(f"WRITING_PROFILE 配置引用来源损坏：{path}") from exc
        return {}


def load_writing_profile(project_root: Path, *, state: dict[str, Any] | None = None) -> WritingProfile:
    root = Path(project_root)
    path = root / PROFILE_PATH
    if path.exists():
        try:
            profile = WritingProfile.model_validate_json(path.read_text(encoding="utf-8"))
            load_rule_bundles(profile)
            return profile
        except (OSError, ValueError, KeyError) as exc:
            raise WritingProfileError(f"WRITING_PROFILE 缺损或包版本不匹配：{exc}") from exc
    state = state if state is not None else _read_marker_source(root / ".webnovel" / "state.json")
    master = _read_marker_source(root / ".story-system" / "MASTER_SETTING.json")
    if not isinstance(state, dict):
        raise WritingProfileError("WRITING_PROFILE 状态来源必须是 JSON 对象")
    marked = _has_markers(state) or _has_markers(master)
    # A copied chapter/review/volume still proves an explicit configuration even
    # if both the profile and master/state have been accidentally removed.
    if not marked:
        for folder in ("chapters", "volumes", "reviews", "commits"):
            for candidate in (root / ".story-system" / folder).glob("*.json"):
                if _has_markers(_read_marker_source(candidate)):
                    marked = True
                    break
            if marked:
                break
    if marked:
        raise WritingProfileError("WRITING_PROFILE.json 缺失；项目已有显式配置标记，拒绝回落到国内默认值")
    info = state.get("project_info") or state.get("project") or {}
    # Keep historical unregistered labels usable; this object is never persisted
    # and is explicitly marked as a legacy reference.
    raw = str(info.get("genre_label") or info.get("genre") or "爽文/系统流")
    try:
        genres = resolve_genres(raw, None, "domestic")
    except ValueError:
        genres = [raw]
    profile = WritingProfile(primary_genre=genres[0], secondary_genres=genres[1:], chapter_length=3000,
                             chapter_unit="characters", rule_pack_versions={"domestic-legacy": DOMESTIC_RULE_VERSION},
                             language_pack_version="1.0.0")
    profile._legacy = True
    return profile


def save_writing_profile(project_root: Path, profile: WritingProfile) -> None:
    load_rule_bundles(profile)
    path = Path(project_root) / PROFILE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    # Lock the complete compare-and-create operation as well as atomic replace.
    with FileLock(str(path) + ".init.lock"):
        if path.exists():
            current = load_writing_profile(Path(project_root))
            if current.to_snapshot() != profile.to_snapshot():
                raise WritingProfileError("已有 WritingProfile 与本次选择不同，拒绝覆盖；请使用原配置继续项目")
            return
        atomic_write_json(path, profile.to_snapshot(), use_lock=True, backup=False)
