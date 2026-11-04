#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Tuple

from chapter_outline_loader import load_chapter_plot_structure, volume_num_for_chapter_from_state

from .story_contract_schema import MasterSetting, ReviewContract, VolumeBrief
from .story_contracts import read_json_if_exists
from .profile_contracts import contract_profile_errors
from .writing_profile import load_writing_profile, load_rule_bundles
from .editorial_guidance import build_editorial_guidance


class RuntimeContractBuilder:
    def __init__(self, project_root: Path):
        self.project_root = Path(project_root)

    def build_for_chapter(self, chapter: int) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        master = self._load_master_setting()
        anti_patterns = self._load_anti_patterns()
        plot = self._load_plot_structure(chapter)
        volume = self._resolve_volume(chapter)
        profile = load_writing_profile(self.project_root)
        errors = contract_profile_errors(self.project_root, {"master": master.model_dump()})
        if errors:
            raise ValueError("; ".join(errors))
        bundles = load_rule_bundles(profile) if not profile.reference().get("legacy") else {}
        editorial = build_editorial_guidance(profile, bundles) if bundles else {}
        inherited_meta = master.meta.model_dump(exclude={"contract_type"})

        volume_brief = VolumeBrief.model_validate(
            {
                "meta": {**inherited_meta, "contract_type": "VOLUME_BRIEF"},
                "volume_goal": {"summary": f"第{volume}卷延续 {master.route.get('primary_genre', '')} 的主冲突"},
                "selected_tropes": [master.route.get("primary_genre", ""), *(master.route.get("secondary_genres") or [])],
                "selected_pacing": {"wave": master.master_constraints.get("pacing_strategy", "")},
                "selected_scenes": list(plot.get("cpns") or []),
                "anti_patterns": [row.get("text", "") for row in anti_patterns if row.get("text")],
                "system_constraints": [master.master_constraints.get("core_tone", "")] if master.master_constraints.get("core_tone") else [],
                "editorial_guidance": editorial,
                "overrides": {"locked": {}, "append_only": {}, "override_allowed": {}},
            }
        ).model_dump()
        review_contract = ReviewContract.model_validate(
            {
                "meta": {**inherited_meta, "contract_type": "REVIEW_CONTRACT", "chapter": chapter},
                "must_check": list(plot.get("mandatory_nodes") or []),
                "blocking_rules": list(plot.get("prohibitions") or []),
                "genre_specific_risks": [master.route.get("primary_genre", "")] if master.route.get("primary_genre") else [],
                "anti_patterns": volume_brief["anti_patterns"],
                "system_constraints": volume_brief["system_constraints"],
                "review_thresholds": {"blocking_count": 0, "missed_nodes": 0},
                "language_advisory": bundles.get("language_rules") or {},
                "editorial_guidance": editorial,
                "aesthetics_advisory": [{"genre": pack["id"], "review_focus": pack.get("review_focus", {})} for pack in bundles.get("genre_rules") or []],
                "overrides": {"locked": {}, "append_only": {}, "override_allowed": {}},
            }
        ).model_dump()
        return volume_brief, review_contract

    def _load_master_setting(self) -> MasterSetting:
        raw = read_json_if_exists(self.project_root / ".story-system" / "MASTER_SETTING.json") or {}
        return MasterSetting.model_validate(raw)

    def _load_anti_patterns(self) -> list[Dict[str, Any]]:
        raw = read_json_if_exists(self.project_root / ".story-system" / "anti_patterns.json") or []
        return list(raw)

    def _load_plot_structure(self, chapter: int) -> Dict[str, Any]:
        raw = load_chapter_plot_structure(self.project_root, chapter) or {}
        return {
            "mandatory_nodes": list(raw.get("mandatory_nodes") or []),
            "prohibitions": list(raw.get("prohibitions") or []),
            "cpns": list(raw.get("cpns") or []),
        }

    def _resolve_volume(self, chapter: int) -> int:
        return volume_num_for_chapter_from_state(self.project_root, chapter) or 1
