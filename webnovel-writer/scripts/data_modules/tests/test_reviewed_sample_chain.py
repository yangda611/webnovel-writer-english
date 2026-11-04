"""Actual editorial samples traverse the same project commit/read-model chain."""

import importlib
import hashlib
import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from data_modules.chapter_commit_service import ChapterCommitService
from data_modules.config import DataModulesConfig
from data_modules.context_manager import ContextManager
from data_modules.index_manager import IndexManager
from data_modules.projections import replay_projections, retry_projection
from data_modules.run_ledger import record_write_step
from data_modules.text_metrics import chapter_measurement
from data_modules.writing_profile import load_writing_profile
from data_modules.write_gates import run_write_gate
from init_project import init_project
from status_reporter import StatusReporter


REPO_ROOT = Path(__file__).resolve().parents[4]
SAMPLES_ROOT = REPO_ROOT / "docs" / "research" / "overseas-quality-round2"
CASES = [
    ("progression-fantasy", "", "progression_fantasy", "en"),
    ("litrpg", "en", "litrpg", "en"),
    ("litrpg", "zh", "litrpg", "zh"),
    ("romantasy", "", "romantasy", "en"),
]


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


@pytest.mark.parametrize("case,language_dir,genre,language", CASES)
def test_reviewed_actual_chapters_traverse_commit_projection_and_dashboard(
    tmp_path, monkeypatch, case, language_dir, genre, language
):
    import init_project as init_module
    import story_system

    monkeypatch.setattr(init_module, "is_git_available", lambda: False)
    monkeypatch.setattr(init_module, "write_current_project_pointer", lambda root: None)
    title = f"样章链路-{genre}"
    init_project(str(tmp_path), title, genre, market="overseas", body_language=language,
                 protagonist_name="Sample Protagonist", allow_draft_rules=True)
    profile = load_writing_profile(tmp_path)
    profile_bytes = (tmp_path / ".story-system" / "WRITING_PROFILE.json").read_bytes()
    assert profile.primary_genre == genre
    assert profile.market == "overseas"
    assert profile.body_language == language

    source_dir = SAMPLES_ROOT / case
    if language_dir:
        source_dir /= language_dir
    source_dir /= "正文"
    outline = tmp_path / "大纲" / "第1卷-章节大纲.md"
    outline.write_text(
        "# 第1卷\n\n"
        "## 第1章：样章第一章\n- 核心目标：建立题材承诺与人物当下选择\n- 必须覆盖：当下目标\n\n"
        "## 第2章：样章第二章\n- 核心目标：承接前章限制与代价，推进题材承诺\n- 必须覆盖：前章后果\n",
        encoding="utf-8",
    )

    service = ChapterCommitService(tmp_path)
    expected_total = 0
    for chapter in (1, 2):
        source = source_dir / f"第{chapter:04d}章.md"
        review_path = source_dir.parent / "reviews" / f"chapter_{chapter:03d}.reviewer.json"
        review_report = source_dir.parent / "独立审稿.md"
        prose = source.read_text(encoding="utf-8")
        review = json.loads(review_path.read_text(encoding="utf-8"))
        source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
        assert source_hash in review_report.read_text(encoding="utf-8").lower()
        assert review["chapter"] == chapter
        assert review["blocking_count"] == 0

        query = "承接前章限制与代价，推进题材承诺" if chapter == 2 else "建立题材承诺与人物当下选择"
        monkeypatch.setattr(sys, "argv", [
            "story_system", query, "--project-root", str(tmp_path), "--genre", genre,
            "--chapter", str(chapter), "--persist", "--emit-runtime-contracts",
        ])
        story_system.main()

        context = ContextManager(DataModulesConfig.from_project_root(tmp_path)).build_context(chapter)
        assert context["prewrite_validation"]["blocking"] is False
        assert context["genre_profile"]["genre"] == genre
        assert context["writing_guidance"]["language_rules"]["body_language"] == language
        assert run_write_gate(tmp_path, chapter=chapter, stage="prewrite")["ok"]

        manuscript = tmp_path / "正文" / f"第{chapter:04d}章.md"
        manuscript.parent.mkdir(parents=True, exist_ok=True)
        manuscript.write_text(prose, encoding="utf-8")
        measured = chapter_measurement(tmp_path, chapter)
        expected_total += measured["word_count"]
        artifacts = {
            "review_results": review,
            # This integration isolates review-gated persistence; it does not
            # claim automated outline fulfillment or semantic fact extraction.
            "fulfillment_result": {
                "planned_nodes": [], "covered_nodes": [], "missed_nodes": [], "extra_nodes": []
            },
            "disambiguation_result": {"pending": []},
            "extraction_result": {
                "accepted_events": [], "state_deltas": [], "entity_deltas": [],
                "summary_text": "收录已审读样章；本链路测试不验证事实抽取。",
            },
        }
        for name, payload in artifacts.items():
            _write_json(tmp_path / ".webnovel" / "tmp" / f"{name}.json", payload)
        record_write_step(tmp_path, chapter=chapter, step="draft", status="completed",
                          outputs={"chapter_file": manuscript})
        assert run_write_gate(tmp_path, chapter=chapter, stage="precommit")["ok"]
        commit = service.build_commit(
            chapter, artifacts["review_results"], artifacts["fulfillment_result"],
            artifacts["disambiguation_result"], artifacts["extraction_result"],
        )
        assert commit["meta"]["status"] == "accepted"
        service.apply_projections(commit)
        state = json.loads((tmp_path / ".webnovel" / "state.json").read_text(encoding="utf-8"))
        assert state["progress"]["total_words"] == expected_total
        assert state["progress"]["count_unit"] == profile.chapter_unit

    replay = replay_projections(tmp_path, start_chapter=1, end_chapter=2)
    assert replay["ok"]
    assert retry_projection(tmp_path, chapter=2)["ok"]
    state = json.loads((tmp_path / ".webnovel" / "state.json").read_text(encoding="utf-8"))
    assert state["progress"]["total_words"] == expected_total
    manager = IndexManager(DataModulesConfig.from_project_root(tmp_path))
    chapters = [manager.get_chapter(chapter) for chapter in (1, 2)]
    assert sum(row["word_count"] for row in chapters) == expected_total
    assert {row["count_unit"] for row in chapters} == {profile.chapter_unit}

    monkeypatch.syspath_prepend(str(REPO_ROOT / "webnovel-writer"))
    dashboard = importlib.import_module("dashboard.app")
    client = TestClient(dashboard.create_app(tmp_path))
    info = client.get("/api/project/info").json()
    assert info["progress"]["total_words"] == expected_total
    assert info["progress"]["count_unit"] == profile.chapter_unit
    dashboard_chapters = client.get("/api/chapters").json()
    assert sum(row["word_count"] for row in dashboard_chapters) == expected_total
    assert {row["count_unit"] for row in dashboard_chapters} == {profile.chapter_unit}

    reporter = StatusReporter(str(tmp_path))
    assert reporter.load_state()
    reporter.scan_chapters()
    assert sum(row["word_count"] for row in reporter.chapters_data) == expected_total
    assert {row["count_unit"] for row in reporter.chapters_data} == {profile.chapter_unit}

    init_project(str(tmp_path), title, genre)
    assert (tmp_path / ".story-system" / "WRITING_PROFILE.json").read_bytes() == profile_bytes
    assert (tmp_path / "正文" / "第0001章.md").read_text(encoding="utf-8") == (
        source_dir / "第0001章.md"
    ).read_text(encoding="utf-8")
