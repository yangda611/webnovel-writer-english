"""Writing profile provenance shared by generation, runtime and write gates."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .writing_profile import WritingProfile, load_writing_profile


def profile_meta(profile: WritingProfile) -> dict[str, Any]:
    if profile.reference().get("legacy"):
        return {}
    return {
        "market": profile.market,
        "body_language": profile.body_language,
        "writing_profile_ref": profile.reference(),
        "rule_pack_versions": dict(profile.rule_pack_versions),
        "language_pack_version": profile.language_pack_version,
    }


def contract_profile_errors(project_root: Path, contracts: dict[str, Any], *, state=None,
                            require_all: bool = True) -> list[str]:
    """Validate explicit provenance; legacy projects retain their old contract path."""
    try:
        profile = load_writing_profile(project_root, state=state)
    except (ValueError, OSError) as exc:
        return [str(exc)]
    expected = profile_meta(profile)
    if not expected:
        return []
    errors: list[str] = []
    for name, contract in contracts.items():
        if not contract:
            if require_all:
                errors.append(f"{name}: missing contract for explicit writing profile")
            continue
        if not isinstance(contract, dict) or not isinstance(contract.get("meta") or {}, dict):
            errors.append(f"{name}: damaged contract or metadata object")
            continue
        meta = contract.get("meta") or {}
        for field in ("writing_profile_ref", "rule_pack_versions", "language_pack_version"):
            if meta.get(field) != expected[field]:
                errors.append(f"{name}: stale or missing {field}; refresh contracts from WRITING_PROFILE.json")
        for field in ("market", "body_language"):
            if meta.get(field) is not None and meta[field] != expected[field]:
                errors.append(f"{name}: {field} conflicts with WRITING_PROFILE.json")
        if name.lower() in {"master", "master_setting"}:
            route = contract.get("route")
            route_expected = {
                "primary_genre": profile.primary_genre,
                "secondary_genres": profile.secondary_genres,
                "market": profile.market,
                "body_language": profile.body_language,
            }
            if not isinstance(route, dict):
                errors.append(f"{name}: missing or damaged route for WRITING_PROFILE.json")
            else:
                for field, value in route_expected.items():
                    if route.get(field) != value:
                        errors.append(f"{name}: stale or missing route.{field}; refresh from WRITING_PROFILE.json")
            constraints = contract.get("master_constraints") or {}
            if not isinstance(constraints, dict):
                errors.append(f"{name}: damaged master_constraints")
            elif ("writing_profile" in constraints
                  and constraints["writing_profile"] != profile.to_snapshot()):
                errors.append(f"{name}: stale master_constraints.writing_profile; refresh from WRITING_PROFILE.json")
    return errors
