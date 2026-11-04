"""Market-scoped, version-pinned writing rule registry.

Genre identifiers are not inferred from a partially matching compound input.
Every component must resolve; the order defines the primary and secondaries.
"""
from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from typing import Any

from genre_taxonomy import load_genre_taxonomy, resolve_genre_input

RULES_ROOT = Path(__file__).resolve().parents[2] / "references" / "writing-rules"
DOMESTIC_RULE_VERSION = "1.0.0"
_VERSION = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+")
_SPLIT = re.compile(r"[+＋/、,，|;；]+|与")
_ALIASES = {
    "progressionfantasy": "progression_fantasy", "成长奇幻": "progression_fantasy",
    "进阶奇幻": "progression_fantasy", "litrpg": "litrpg", "游戏机制叙事": "litrpg",
    "游戏文学": "litrpg", "romantasy": "romantasy", "奇幻言情": "romantasy",
}


class RulePackError(ValueError):
    pass


def _alias_key(value: str) -> str:
    return re.sub(r"[\s_-]+", "", unicodedata.normalize("NFKC", value).casefold())


def resolve_genres(genre: str, secondary_genres: list[str] | None, market: str) -> list[str]:
    parts = [str(genre or ""), *(secondary_genres or [])]
    tokens = [token.strip() for part in parts for token in _SPLIT.split(part) if token.strip()]
    if not tokens:
        raise RulePackError("必须指定主题材")
    resolved: list[str] = []
    for position, token in enumerate(tokens):
        if market == "overseas":
            key = _ALIASES.get(_alias_key(token))
        else:
            result = resolve_genre_input(token)
            taxonomy = load_genre_taxonomy()
            # The primary input historically permits descriptive prose. Every
            # explicitly supplied secondary must be a registered label/alias;
            # a substring such as "unregistered悬疑garbage" is not a selection.
            lookup_key = re.sub(r"\s+", "", unicodedata.normalize("NFKC", token).lower())
            entry = taxonomy.lookup.get(lookup_key)
            if entry is None and position == 0 and result.matched_labels:
                matched_key = re.sub(r"\s+", "", unicodedata.normalize("NFKC", result.matched_labels[0]).lower())
                entry = taxonomy.lookup.get(matched_key)
            # Registered identities are independent from shared template files:
            # 玄幻 and 仙侠 both use 修仙.md, but remain distinct selections.
            key = entry.label if entry is not None and token != "全部" else None
        if not key:
            raise RulePackError(f"未知{market}题材：{token}；请逐项选择已注册的主辅题材。国内示例：规则怪谈、悬疑、玄幻。")
        if key not in resolved:
            resolved.append(key)
    return resolved


def read_pack(kind: str, pack_id: str, version: str | None = None) -> dict[str, Any]:
    if kind not in {"genres", "languages"} or not re.fullmatch(r"[a-z_]+", pack_id):
        raise RulePackError(f"无效规则包标识：{kind}/{pack_id}")
    path = RULES_ROOT / kind / f"{pack_id}.json"
    if version is not None:
        if not isinstance(version, str) or not _VERSION.fullmatch(version):
            raise RulePackError(f"无效规则包版本：{version!r}")
        archived = RULES_ROOT / "versions" / kind / pack_id / f"{version}.json"
        # A pinned release is independent of the current draft. A damaged
        # archive must fail rather than silently substituting a newer package.
        if not archived.is_file():
            raise RulePackError(f"固定版本归档缺失：{archived}")
        path = archived
    try:
        pack = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise RulePackError(f"规则包缺失或损坏：{path}") from exc
    required = ("id", "version", "status", "market", "reader_promise", "scope", "init_questions",
                "outline_guidance", "writing_guidance", "review_focus", "examples", "sources")
    if not isinstance(pack, dict) or any(not pack.get(field) for field in required):
        raise RulePackError(f"规则包字段不完整：{path}")
    field_types = {"reader_promise": str, "scope": dict, "review_focus": dict,
                   **{field: list for field in ("init_questions", "outline_guidance", "writing_guidance", "examples", "sources")}}
    if any(not isinstance(pack[field], expected) for field, expected in field_types.items()):
        raise RulePackError(f"规则包字段类型错误：{path}")
    if "editorial_framework" in pack:
        framework = pack["editorial_framework"]
        expected_fields = {"evidence_basis": str, "primary_application": str, "secondary_application": str,
                           **{field: list for field in ("promise_horizon", "continuity_ledger", "scene_checks", "contrast_cases")}}
        if not isinstance(framework, dict) or any(
            not isinstance(framework.get(field), expected) or not framework[field]
            for field, expected in expected_fields.items()
        ):
            raise RulePackError(f"规则包编辑框架字段缺损：{path}")
    if "scene_revision_checks" in pack and not isinstance(pack["scene_revision_checks"], list):
        raise RulePackError(f"语言包复核字段类型错误：{path}")
    if pack["id"] != pack_id or pack["status"] not in {"draft", "verified"}:
        raise RulePackError(f"规则包标识或状态不匹配：{path}")
    if not isinstance(pack["version"], str) or not _VERSION.fullmatch(pack["version"]):
        raise RulePackError(f"无效规则包版本：{path}")
    if version is not None and pack["version"] != version:
        raise RulePackError(f"规则包版本不匹配：{pack_id}，项目 {version}，安装 {pack['version']}")
    expected_market = "overseas" if kind == "genres" else "shared"
    if pack["market"] != expected_market:
        raise RulePackError(f"规则包市场范围不匹配：{path}")
    if kind == "languages" and pack.get("body_language") != pack_id:
        raise RulePackError(f"语言包正文语言不匹配：{path}")
    return pack


def genre_versions(genres: list[str], market: str) -> dict[str, str]:
    if market == "domestic":
        return {"domestic-legacy": DOMESTIC_RULE_VERSION}
    return {key: read_pack("genres", key)["version"] for key in genres}
