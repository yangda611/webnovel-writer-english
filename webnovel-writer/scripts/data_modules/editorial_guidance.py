"""Compile selected advice, keeping genre roles separate from prose language.

This editorial aid does not infer facts, grade prose or add blockers. Older
pinned packages remain usable without the newer editorial framework.
"""
from __future__ import annotations

from typing import Any

from .writing_profile import WritingProfile


def build_editorial_guidance(profile: WritingProfile, bundles: dict[str, Any]) -> dict[str, Any]:
    if profile.market != "overseas":
        return {}
    roles = []
    for pack in bundles["genre_rules"]:
        framework = pack.get("editorial_framework") or {}
        primary = pack["id"] == profile.primary_genre
        role = "primary" if primary else "secondary"
        roles.append({
            "genre": pack["id"], "role": role, "version": pack["version"], "status": pack["status"],
            "reader_promise": pack["reader_promise"],
            "application": framework.get(f"{role}_application") or pack["reader_promise"],
            "secondary_application": framework.get("secondary_application", ""),
            "promise_horizon": framework.get("promise_horizon", []),
            "continuity_ledger": framework.get("continuity_ledger", []),
            "scene_checks": framework.get("scene_checks", []),
            "contrast_cases": framework.get("contrast_cases", []),
            "evidence_basis": framework.get("evidence_basis") or pack.get("scope", {}).get("evidence_status", ""),
        })
    language = bundles["language_rules"]
    return {
        "advisory_only": True,
        "writing_profile_ref": profile.reference(),
        "composition_policy": "主类型决定主要回报，辅类型按本书约定参与；保留全部辅类型，不要求每章兑现全部承诺。冲突时依据作者已选目标权衡，不自动覆盖任一类型。",
        "evidence_policy": "以具体正文、前章后果和已选承诺提出建议；未兑现可记录为铺垫。编辑账本只引用已确认事实，不成为新的事实真源或审美阻断。",
        "genre_roles": roles,
        "language": {
            "body_language": profile.body_language, "version": language["version"],
            "pov": profile.pov, "tense": profile.tense,
            "expression_guidance": language.get("expression_guidance", {}),
            "scene_revision_checks": language.get("scene_revision_checks", []),
        },
    }
