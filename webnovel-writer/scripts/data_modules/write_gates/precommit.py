#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path

try:
    from chapter_paths import find_chapter_file
except ImportError:  # pragma: no cover
    from scripts.chapter_paths import find_chapter_file

from ..artifact_validator import validate_commit_artifact_files
from ..profile_contracts import contract_profile_errors
from ..story_runtime_sources import load_runtime_sources
from ..project_phase import (
    COMMIT_ARTIFACT_FILES,
    PHASE_INIT_READY,
    PHASE_INIT_SCAFFOLDED,
    PHASE_NO_PROJECT,
    PHASE_PLAN_IN_PROGRESS,
    PHASE_PROJECTION_FAILED,
    resolve_project_phase,
)
from . import gate_report, issue


BLOCKED_PRECOMMIT_PHASES = {
    PHASE_NO_PROJECT,
    PHASE_INIT_SCAFFOLDED,
    PHASE_INIT_READY,
    PHASE_PLAN_IN_PROGRESS,
    PHASE_PROJECTION_FAILED,
}


def _artifact_paths(project_root: Path) -> dict[str, Path]:
    return {
        "review_result": project_root / COMMIT_ARTIFACT_FILES[0],
        "fulfillment_result": project_root / COMMIT_ARTIFACT_FILES[1],
        "disambiguation_result": project_root / COMMIT_ARTIFACT_FILES[2],
        "extraction_result": project_root / COMMIT_ARTIFACT_FILES[3],
    }


def run_precommit_gate(project_root: Path, chapter: int) -> dict:
    snapshot = resolve_project_phase(project_root, chapter=chapter)
    errors: list[dict] = []
    warnings: list[dict] = []

    try:
        contracts = load_runtime_sources(project_root, chapter).contracts
        profile_errors = contract_profile_errors(project_root, contracts)
    except (ValueError, OSError) as exc:
        profile_errors = [str(exc)]
    if profile_errors:
        errors.append(issue(
            "writing_profile_contract_mismatch",
            message="; ".join(profile_errors),
            impact="本次正文与当前项目配置的合同绑定无法确认，不能提交。",
            repair="恢复 WRITING_PROFILE.json，并基于原配置刷新本章全部合同后重新检查。",
        ))

    if snapshot.phase in BLOCKED_PRECOMMIT_PHASES:
        errors.append(
            issue(
                "phase_not_ready_for_precommit",
                message=f"phase {snapshot.phase} is not ready for precommit",
                impact="项目骨架、规划合同或上一轮投影状态不完整，继续提交会固化不可靠事实。",
                repair="先运行 project-status/doctor，并按 next_action 修复当前阶段问题。",
                details=snapshot.to_dict(),
            )
        )

    chapter_file = find_chapter_file(project_root, chapter)
    if chapter_file is None:
        errors.append(
            issue(
                "chapter_file_missing",
                message=f"chapter {chapter} file missing",
                path=str(project_root / "正文"),
                impact="没有可提交的正文文件。",
                repair="先完成正文起草并保存到 正文/。",
            )
        )
    elif not chapter_file.read_text(encoding="utf-8").strip():
        errors.append(
            issue(
                "chapter_file_empty",
                message=f"chapter {chapter} file is empty",
                path=str(chapter_file),
                impact="空正文不能提交为章节事实。",
                repair="补齐正文内容后再提交。",
            )
        )

    paths = _artifact_paths(project_root)
    artifact_report = validate_commit_artifact_files(
        review_result=paths["review_result"],
        fulfillment_result=paths["fulfillment_result"],
        disambiguation_result=paths["disambiguation_result"],
        extraction_result=paths["extraction_result"],
    )
    for item in artifact_report.get("errors") or []:
        errors.append(
            issue(
                f"artifact.{item.get('type')}",
                message=str(item.get("message") or ""),
                path=str(item.get("path") or ""),
                impact=str(item.get("impact") or ""),
                repair=str(item.get("repair") or ""),
                details=item,
            )
        )
    for item in artifact_report.get("warnings") or []:
        warnings.append(
            issue(
                f"artifact.{item.get('type')}",
                message=str(item.get("message") or ""),
                severity="warning",
                path=str(item.get("path") or ""),
                details=item,
            )
        )

    return gate_report(
        stage="precommit",
        project_root=project_root,
        chapter=chapter,
        phase=snapshot.phase,
        errors=errors,
        warnings=warnings,
        details={
            "phase": snapshot.to_dict(),
            "chapter_file": str(chapter_file) if chapter_file else "",
            "artifact_report": artifact_report,
        },
    )
