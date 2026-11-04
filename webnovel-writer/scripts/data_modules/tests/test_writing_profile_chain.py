"""Three real project flows, separate from editorial sample-quality assessment."""
import json
import sys
from pathlib import Path

import pytest

from data_modules.chapter_commit_service import ChapterCommitService
from data_modules.config import DataModulesConfig
from data_modules.context_manager import ContextManager
from data_modules.index_manager import IndexManager
from data_modules.projections import format_projection_report, replay_projections, retry_projection
from data_modules.run_ledger import build_write_resume_plan, record_write_step
from data_modules.story_contracts import StoryContractPaths
from data_modules.write_gates import format_gate_report, run_write_gate
from data_modules.writing_profile import load_writing_profile
from init_project import init_project


def _json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


@pytest.mark.parametrize("market,language,genre", [
    ("domestic", "zh", "规则怪谈+悬疑"),
    ("overseas", "zh", "progression_fantasy+litrpg+romantasy"),
    ("overseas", "en", "progression_fantasy+litrpg+romantasy"),
])
def test_init_refresh_context_prewrite_commit_replay_chain(tmp_path, monkeypatch, capsys, market, language, genre):
    import init_project as init_module
    import story_system

    monkeypatch.setattr(init_module, "is_git_available", lambda: False)
    monkeypatch.setattr(init_module, "write_current_project_pointer", lambda root: None)
    init_project(str(tmp_path), "桥的代价", genre, market=market, body_language=language,
                 protagonist_name="Maeve O’Connell", allow_draft_rules=True)
    profile = load_writing_profile(tmp_path)
    before = (tmp_path / ".story-system/WRITING_PROFILE.json").read_bytes()
    # The plan is management text; prose language does not change internal paths.
    (tmp_path / "大纲/第1卷-章节大纲.md").write_text(
        "# 第1卷\n\n## 第1章：桥的代价\n- 核心目标：发现桥上的符号，付出代价后过桥\n- 必须覆盖：发现符号\n", encoding="utf-8")
    for query in ("发现桥上的符号", "付出代价后过桥"):
        monkeypatch.setattr(sys, "argv", ["story_system", query, "--project-root", str(tmp_path),
                                         "--genre", genre, "--chapter", "1", "--persist", "--emit-runtime-contracts"])
        story_system.main()
    assert (tmp_path / ".story-system/WRITING_PROFILE.json").read_bytes() == before
    paths = StoryContractPaths.from_project_root(tmp_path)
    for path in (paths.master_json, paths.chapter_json(1), paths.volume_json(1), paths.review_json(1)):
        assert json.loads(path.read_text(encoding="utf-8"))["meta"]["writing_profile_ref"] == profile.reference()

    context = ContextManager(DataModulesConfig.from_project_root(tmp_path)).build_context(1)
    assert context["prewrite_validation"]["blocking"] is False
    assert context["genre_profile"]["secondary_genres"] == profile.secondary_genres
    if market == "overseas":
        assert context["writing_guidance"]["language_rules"]["body_language"] == language
        assert "shuangwen" not in json.dumps(context, ensure_ascii=False)
    prewrite = run_write_gate(tmp_path, chapter=1, stage="prewrite")
    assert prewrite["ok"], prewrite
    assert "OK write-gate prewrite" in format_gate_report(prewrite, "text")

    manuscript = tmp_path / "正文/第0001章.md"
    prose = "The old bridge crossed the river beneath a pale sky." if language == "en" else "梅芙认出了桥上的符号。她留下最后一枚铜币，踏上桥面。"
    manuscript.write_text("# 第1章\n\n" + prose, encoding="utf-8")
    artifacts = {
        "review_results": {"blocking_count": 0, "language_advisory": ["句式可再斟酌，但不构成事实阻断"]},
        "fulfillment_result": {"planned_nodes": ["发现符号"], "covered_nodes": ["发现符号"], "missed_nodes": [], "extra_nodes": []},
        "disambiguation_result": {"pending": []},
        "extraction_result": {"accepted_events": [], "state_deltas": [], "entity_deltas": [],
                              "summary_text": "梅芙发现桥上符号并付出代价过桥。"},
    }
    for name, payload in artifacts.items():
        _json(tmp_path / f".webnovel/tmp/{name}.json", payload)
    record_write_step(tmp_path, chapter=1, step="draft", status="completed", outputs={"chapter_file": manuscript})
    assert run_write_gate(tmp_path, chapter=1, stage="precommit")["ok"]
    service = ChapterCommitService(tmp_path)
    commit = service.build_commit(1, artifacts["review_results"], artifacts["fulfillment_result"],
                                  artifacts["disambiguation_result"], artifacts["extraction_result"])
    assert commit["meta"]["status"] == "accepted"
    projected = service.apply_projections(commit)
    assert projected["projection_status"]["state"] == "done"
    assert projected["projection_status"]["index"] == "done"
    assert projected["projection_status"]["summary"] == "done"
    first = json.loads((tmp_path / ".webnovel/state.json").read_text(encoding="utf-8"))["progress"]["total_words"]
    replay = replay_projections(tmp_path, start_chapter=1, end_chapter=1)
    assert replay["ok"] and "OK projections replay" in format_projection_report(replay, "text")
    assert retry_projection(tmp_path, chapter=1)["ok"]
    state = json.loads((tmp_path / ".webnovel/state.json").read_text(encoding="utf-8"))
    assert state["progress"]["total_words"] == first
    assert state["project_info"]["writing_profile"] == profile.to_snapshot()
    chapter = IndexManager(DataModulesConfig.from_project_root(tmp_path)).get_chapter(1)
    assert chapter["word_count"] == first
    assert chapter["count_unit"] == profile.chapter_unit
    assert run_write_gate(tmp_path, chapter=1, stage="postcommit")["ok"]
    plan = build_write_resume_plan(tmp_path, chapter=1)
    assert all(item["action"] == "skip" for item in plan["steps"] if item["step"] in {"draft", "commit", "projection"})
    init_project(str(tmp_path), "桥的代价", genre)
    assert load_writing_profile(tmp_path).reference() == profile.reference()
    # Editing a valid configuration after drafting invalidates its contracts at
    # submission too; callers may invoke precommit without a fresh prewrite.
    profile_path = tmp_path / ".story-system/WRITING_PROFILE.json"
    changed = profile.to_snapshot()
    changed["chapter_length"] += 100
    profile_path.write_text(json.dumps(changed), encoding="utf-8")
    stale = run_write_gate(tmp_path, chapter=1, stage="precommit")
    assert not stale["ok"]
    assert any(item["code"] == "writing_profile_contract_mismatch" for item in stale["errors"])
