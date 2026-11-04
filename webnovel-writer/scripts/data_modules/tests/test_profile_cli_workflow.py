"""Public CLI boundaries preserve Unicode project data and resume provenance."""
import json
import sys

import pytest

from data_modules import context_manager, projections, run_ledger, webnovel
from data_modules.writing_profile import build_writing_profile, save_writing_profile


def _book(root):
    profile = build_writing_profile(market="overseas", body_language="en",
                                    genre="progression_fantasy+litrpg+romantasy", allow_draft_rules=True)
    save_writing_profile(root, profile)
    state = root / ".webnovel/state.json"
    state.parent.mkdir(exist_ok=True)
    state.write_text(json.dumps({"project_info": {"title": "桥与誓言", "writing_profile": profile.to_snapshot()},
                                 "protagonist_state": {"name": "Maeve O’Connell"}}), encoding="utf-8")
    return profile


def _call(monkeypatch, main, root, *args):
    monkeypatch.setattr(sys, "argv", ["cli", "--project-root", str(root), *args])
    return main()


def test_context_cli_preserves_profile_and_reports_missing_explicit_configuration(tmp_path, monkeypatch, capsys):
    profile = _book(tmp_path)
    _call(monkeypatch, context_manager.main, tmp_path, "--chapter", "1")
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "success"
    assert result["data"]["genre_profile"]["secondary_genres"] == ["litrpg", "romantasy"]
    assert result["data"]["writing_guidance"]["language_rules"]["body_language"] == "en"
    assert result["data"]["core"]["protagonist_snapshot"]["name"] == "Maeve O’Connell"
    assert "shuangwen" not in json.dumps(result)
    (tmp_path / profile.reference()["path"]).unlink()
    _call(monkeypatch, context_manager.main, tmp_path, "--chapter", "1")
    failure = json.loads(capsys.readouterr().out)
    assert failure["status"] == "error"
    assert failure["error"]["code"] == "CONTEXT_BUILD_FAILED"
    assert "WRITING_PROFILE" in failure["error"]["message"]


def test_run_ledger_cli_records_english_manuscript_in_chinese_path_and_detects_revision(tmp_path, monkeypatch, capsys):
    profile = _book(tmp_path)
    chapter = tmp_path / "正文/第0001章.md"
    chapter.parent.mkdir()
    chapter.write_text("Maeve O’Connell crossed the bridge.", encoding="utf-8")
    args = ["record-write-step", "--chapter", "1", "--step", "draft", "--status", "completed",
            "--inputs-json", json.dumps({"writing_profile": str(tmp_path / profile.reference()["path"])}),
            "--outputs-json", json.dumps({"chapter_file": str(chapter)}),
            "--auto-handled-json", '["英文人名保留"]', "--duration-ms", "17"]
    _call(monkeypatch, run_ledger.main, tmp_path, *args)
    entry = json.loads(capsys.readouterr().out)
    assert entry["outputs"]["chapter_file"]["exists"] is True
    assert entry["inputs"]["writing_profile"]["sha256"]
    assert entry["auto_handled"] == ["英文人名保留"]
    _call(monkeypatch, run_ledger.main, tmp_path, "write-resume", "--chapter", "1", "--format", "text")
    assert "draft: skip" in capsys.readouterr().out
    chapter.write_text("Maeve O’Connell kept the oath.", encoding="utf-8")
    _call(monkeypatch, run_ledger.main, tmp_path, "write-resume", "--chapter", "1")
    resume = json.loads(capsys.readouterr().out)
    assert next(step for step in resume["steps"] if step["step"] == "draft")["action"] != "skip"
    _call(monkeypatch, run_ledger.main, tmp_path, *args, "--format", "text")
    assert capsys.readouterr().out.strip() == "draft: completed"


@pytest.mark.parametrize("flag,value,error", [
    ("--inputs-json", "{", "合法 JSON"),
    ("--outputs-json", "[]", "JSON object"),
    ("--problems-json", "{}", "JSON list"),
])
def test_standalone_ledger_cli_invalid_payload_does_not_create_ledger(tmp_path, monkeypatch, flag, value, error):
    _book(tmp_path)
    with pytest.raises(SystemExit, match=error):
        _call(monkeypatch, run_ledger.main, tmp_path, "record-write-step", "--chapter", "1", "--step", "draft",
              "--status", "completed", flag, value)
    assert not (tmp_path / ".webnovel/run_ledger.json").exists()


@pytest.mark.parametrize("flag,value,error", [
    ("--inputs-json", "{", "不合法"),
    ("--outputs-json", "[]", "JSON object"),
    ("--auto-handled-json", "{}", "JSON list"),
])
def test_unified_ledger_cli_invalid_payload_has_exit_code_and_does_not_write(tmp_path, monkeypatch, capsys, flag, value, error):
    _book(tmp_path)
    with pytest.raises(SystemExit) as result:
        _call(monkeypatch, webnovel.main, tmp_path, "run-ledger", "record-write-step", "--chapter", "1", "--step", "draft",
              "--status", "completed", flag, value)
    assert result.value.code == 2
    assert error in capsys.readouterr().err
    assert not (tmp_path / ".webnovel/run_ledger.json").exists()


def test_unified_cli_preflight_text_explains_profile_error(tmp_path, monkeypatch, capsys):
    profile = _book(tmp_path)
    (tmp_path / profile.reference()["path"]).write_text("{", encoding="utf-8")
    with pytest.raises(SystemExit) as result:
        _call(monkeypatch, webnovel.main, tmp_path, "preflight", "--format", "text")
    assert result.value.code == 1
    report = capsys.readouterr().out
    assert "ERROR" in report and "WRITING_PROFILE" in report


def test_domestic_registered_identities_resolve_templates_without_losing_secondaries(tmp_path):
    from data_modules.config import DataModulesConfig
    profile = build_writing_profile(genre="玄幻+仙侠+奇幻")
    save_writing_profile(tmp_path, profile)
    (tmp_path / ".webnovel").mkdir(exist_ok=True)
    (tmp_path / ".webnovel/state.json").write_text("{}", encoding="utf-8")
    result = context_manager.ContextManager(DataModulesConfig.from_project_root(tmp_path)).build_context(1)
    genres = result["genre_profile"]
    assert genres["genres"] == ["玄幻", "仙侠", "奇幻"]
    assert "# 修仙题材模板" in genres["profile_excerpt"]
    assert "# 修仙题材模板" in genres["secondary_profile_excerpts"][0]
    assert "# 西幻题材模板" in genres["secondary_profile_excerpts"][1]


def test_projection_cli_replays_once_and_returns_structured_profile_failure(tmp_path, monkeypatch, capsys):
    from data_modules.chapter_commit_service import ChapterCommitService
    from data_modules.profile_contracts import profile_meta
    from data_modules.story_contracts import StoryContractPaths, write_json

    profile = _book(tmp_path)
    paths = StoryContractPaths.from_project_root(tmp_path)
    for path in (paths.master_json, paths.volume_json(1), paths.chapter_json(1), paths.review_json(1)):
        contract = {"meta": profile_meta(profile)}
        if path == paths.master_json:
            contract["route"] = {
                "primary_genre": profile.primary_genre,
                "secondary_genres": profile.secondary_genres,
                "market": profile.market,
                "body_language": profile.body_language,
            }
            contract["master_constraints"] = {"writing_profile": profile.to_snapshot()}
        write_json(path, contract)
    chapter = tmp_path / "正文/第0001章.md"
    chapter.parent.mkdir()
    chapter.write_text("The old bridge crossed the river beneath a pale sky.", encoding="utf-8")
    service = ChapterCommitService(tmp_path)
    commit = service.build_commit(1, {"blocking_count": 0},
                                  {"planned_nodes": [], "covered_nodes": [], "missed_nodes": [], "extra_nodes": []},
                                  {"pending": []}, {"summary_text": "过桥", "accepted_events": [], "state_deltas": [], "entity_deltas": []})
    assert service.apply_projections(commit)["projection_status"]["state"] == "done"
    for args in (["retry", "--chapter", "1", "--format", "text"],
                 ["replay", "--from-chapter", "1", "--to-chapter", "1"]):
        with pytest.raises(SystemExit) as result:
            _call(monkeypatch, projections.main, tmp_path, *args)
        assert result.value.code == 0
        report = capsys.readouterr().out
        assert "OK projections retry" in report or json.loads(report)["ok"]
    state_before = (tmp_path / ".webnovel/state.json").read_bytes()
    (tmp_path / profile.reference()["path"]).write_text("{", encoding="utf-8")
    with pytest.raises(SystemExit) as result:
        _call(monkeypatch, projections.main, tmp_path, "retry", "--chapter", "1")
    assert result.value.code == 1
    failure = json.loads(capsys.readouterr().out)
    assert failure["ok"] is False and "WRITING_PROFILE" in failure["error"]
    assert (tmp_path / ".webnovel/state.json").read_bytes() == state_before


def test_projection_cli_rejects_invalid_range_without_touching_project(tmp_path, monkeypatch, capsys):
    _book(tmp_path)
    with pytest.raises(SystemExit) as result:
        _call(monkeypatch, projections.main, tmp_path, "replay", "--from-chapter", "2", "--to-chapter", "1", "--format", "text")
    assert result.value.code == 1
    assert "invalid_chapter_range" in capsys.readouterr().out
    assert not (tmp_path / ".story-system/commits").exists()
