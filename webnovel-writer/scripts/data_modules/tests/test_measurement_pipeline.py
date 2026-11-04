"""Accepted chapter counts stay aligned across durable projections and readers."""

import importlib
import json
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from data_modules.chapter_commit_service import ChapterCommitService
from data_modules.config import DataModulesConfig
from data_modules.index_manager import IndexManager
from data_modules.index_projection_writer import IndexProjectionWriter
from data_modules.state_projection_writer import StateProjectionWriter
from data_modules.state_manager import StateManager
from data_modules.text_metrics import chapter_measurement
from data_modules.writing_profile import build_writing_profile, save_writing_profile, load_writing_profile
from data_modules.profile_contracts import profile_meta
from data_modules.story_contracts import StoryContractPaths
from extract_chapter_context import extract_state_summary
from status_reporter import StatusReporter
from update_state import StateUpdater


SAMPLE = "The old bridge crossed the river beneath a pale sky."


def _project(root, market="overseas", language="en"):
    genre = "仙侠" if market == "domestic" else "progression_fantasy"
    profile = build_writing_profile(market=market, body_language=language, genre=genre,
                                    chapter_length=2000, allow_draft_rules=True)
    save_writing_profile(root, profile)
    (root / ".webnovel").mkdir()
    (root / ".webnovel" / "state.json").write_text(
        json.dumps({"writing_profile": profile.to_snapshot(), "progress": {"current_chapter": 0, "total_words": 0}}),
        encoding="utf-8",
    )
    (root / "正文").mkdir()
    path = root / "正文" / "第0001章.md"
    path.write_text(f"# Chapter One\n\n{SAMPLE}\n", encoding="utf-8")
    _seed_contracts(root)
    return path


def _seed_contracts(root, chapter=1):
    paths = StoryContractPaths.from_project_root(root)
    profile = load_writing_profile(root)
    for path in (paths.master_json, paths.volume_json(1), paths.chapter_json(chapter), paths.review_json(chapter)):
        path.parent.mkdir(parents=True, exist_ok=True)
        contract = {"meta": profile_meta(profile)}
        if path == paths.master_json:
            contract["route"] = {
                "primary_genre": profile.primary_genre,
                "secondary_genres": profile.secondary_genres,
                "market": profile.market,
                "body_language": profile.body_language,
            }
            contract["master_constraints"] = {"writing_profile": profile.to_snapshot()}
        path.write_text(json.dumps(contract), encoding="utf-8")


def _commit(root, chapter=1):
    return ChapterCommitService(root).build_commit(
        chapter, {"blocking_count": 0},
        {"planned_nodes": [], "covered_nodes": [], "missed_nodes": [], "extra_nodes": []},
        {"pending": []},
        {"accepted_events": [], "state_deltas": [], "entity_deltas": [],
         "chapter_meta": {"word_count": 9999, "count_unit": "characters"}},
    )


@pytest.mark.parametrize(
    "market, language, expected, unit",
    [("domestic", "zh", 52, "characters"), ("overseas", "zh", 52, "characters"),
     ("overseas", "en", 10, "words")],
)
def test_commit_state_index_dashboard_and_report_share_counts(tmp_path, monkeypatch, market, language, expected, unit):
    _project(tmp_path, market, language)
    service = ChapterCommitService(tmp_path)
    payload = _commit(tmp_path)
    assert payload["extraction_result"]["chapter_meta"]["word_count"] == expected
    assert payload["extraction_result"]["chapter_meta"]["count_unit"] == unit
    for _ in range(2):
        result = service.apply_projections(payload)
        assert result["projection_status"]["state"] == "done"
        assert result["projection_status"]["index"] == "done"
    state = json.loads((tmp_path / ".webnovel" / "state.json").read_text(encoding="utf-8"))
    assert state["progress"]["total_words"] == expected
    assert state["progress"]["count_unit"] == unit
    chapter = IndexManager(DataModulesConfig.from_project_root(tmp_path)).get_chapter(1)
    assert chapter["word_count"] == expected
    assert chapter["count_unit"] == unit

    plugin_root = Path(__file__).resolve().parents[3]
    monkeypatch.syspath_prepend(str(plugin_root))
    module = importlib.import_module("dashboard.app")
    client = TestClient(module.create_app(tmp_path))
    assert client.get("/api/project/info").json()["progress"]["count_unit"] == unit
    displayed = client.get("/api/chapters").json()[0]
    assert (displayed["word_count"], displayed["count_unit"]) == (expected, unit)
    trend = client.get("/api/stats/chapter-trend").json()
    assert trend["count_unit"] == unit
    assert (trend["items"][0]["word_count"], trend["items"][0]["count_unit"]) == (expected, unit)

    reporter = StatusReporter(str(tmp_path))
    assert reporter.load_state()
    reporter.scan_chapters()
    assert reporter.chapters_data[0]["word_count"] == expected
    assert reporter.chapters_data[0]["count_unit"] == unit
    report = "\n".join(reporter._generate_basic_stats())
    suffix = "词" if language == "en" else "字"
    assert f"{expected:,} {suffix}" in report
    assert f"{expected}{suffix}" in extract_state_summary(tmp_path)


def test_replay_recounts_revised_chapters_including_empty_manuscript(tmp_path):
    manuscript = _project(tmp_path)
    payload = _commit(tmp_path)
    for revised, expected in [(SAMPLE, 10), ("Only two.", 2), ("# Heading only\n", 0)]:
        manuscript.write_text(revised, encoding="utf-8")
        StateProjectionWriter(tmp_path).apply(payload)
        IndexProjectionWriter(tmp_path).apply(payload)
        state = json.loads((tmp_path / ".webnovel" / "state.json").read_text(encoding="utf-8"))
        assert state["progress"]["total_words"] == expected
        chapter = IndexManager(DataModulesConfig.from_project_root(tmp_path)).get_chapter(1)
        assert chapter["word_count"] == expected


def test_explicit_project_missing_manuscript_cannot_accept_imported_count(tmp_path):
    _project(tmp_path).unlink()
    payload = {"meta": {"chapter": 1, "status": "accepted"}, "word_count": 9999}
    with pytest.raises(FileNotFoundError, match="正文"):
        IndexProjectionWriter(tmp_path).apply(payload)
    with pytest.raises(FileNotFoundError, match="正文"):
        StateProjectionWriter(tmp_path).apply(payload)


def test_legacy_index_can_still_import_metadata_without_manuscript(tmp_path):
    payload = {"meta": {"chapter": 1, "status": "accepted"}, "word_count": 123}
    IndexProjectionWriter(tmp_path).apply(payload)
    chapter = IndexManager(DataModulesConfig.from_project_root(tmp_path)).get_chapter(1)
    assert chapter["word_count"] == 123
    assert chapter["count_unit"] == "characters"


def test_legacy_metadata_only_accepted_commit_has_identical_state_and_index_count(tmp_path):
    payload = {"meta": {"chapter": 1, "status": "accepted"},
               "extraction_result": {"chapter_meta": {"word_count": 123}}}
    result = ChapterCommitService(tmp_path).apply_projections(payload)
    assert result["projection_status"]["state"] == "done"
    assert result["projection_status"]["index"] == "done"
    state = json.loads((tmp_path / ".webnovel" / "state.json").read_text(encoding="utf-8"))
    chapter = IndexManager(DataModulesConfig.from_project_root(tmp_path)).get_chapter(1)
    assert (state["progress"]["total_words"], chapter["word_count"]) == (123, 123)
    assert (state["progress"]["count_unit"], chapter["count_unit"]) == ("characters", "characters")


def test_replay_refreshes_persisted_commit_measurement(tmp_path):
    manuscript = _project(tmp_path)
    service = ChapterCommitService(tmp_path)
    payload = _commit(tmp_path)
    manuscript.write_text("Only two.", encoding="utf-8")
    service.apply_projection_writers(payload)
    saved = json.loads((tmp_path / ".story-system" / "commits" / "chapter_001.commit.json").read_text(encoding="utf-8"))
    assert saved["extraction_result"]["chapter_meta"]["word_count"] == 2


def test_old_index_schema_gains_explicit_character_unit_without_losing_data(tmp_path):
    config = DataModulesConfig.from_project_root(tmp_path)
    config.ensure_dirs()
    with sqlite3.connect(config.index_db) as conn:
        conn.execute("CREATE TABLE chapters (chapter INTEGER PRIMARY KEY, title TEXT, location TEXT, word_count INTEGER, characters TEXT, summary TEXT)")
        conn.execute("INSERT INTO chapters VALUES (1, '旧章', '', 42, '[]', '原摘要')")
    chapter = IndexManager(config).get_chapter(1)
    assert (chapter["word_count"], chapter["count_unit"], chapter["summary"]) == (42, "characters", "原摘要")


def test_direct_progress_readers_keep_profile_unit(tmp_path, capsys):
    _project(tmp_path)
    manager = StateManager(DataModulesConfig.from_project_root(tmp_path), enable_sqlite_sync=False)
    manager.update_progress(1, 10)
    manager.save_state()
    saved = json.loads((tmp_path / ".webnovel" / "state.json").read_text(encoding="utf-8"))
    assert saved["progress"]["count_unit"] == "words"
    updater = StateUpdater(str(tmp_path / ".webnovel" / "state.json"))
    updater.state = json.loads((tmp_path / ".webnovel" / "state.json").read_text(encoding="utf-8"))
    updater.update_progress(1, 10)
    assert updater.state["progress"]["count_unit"] == "words"
    assert "总词数" in capsys.readouterr().out


def test_overseas_report_does_not_apply_domestic_pacing_thresholds(tmp_path, monkeypatch):
    _project(tmp_path)
    reporter = StatusReporter(str(tmp_path))
    reporter.load_state()
    reporter.scan_chapters()
    reporter.chapters_data[0]["cool_point"] = "胜利"
    monkeypatch.setattr(reporter, "_get_pacing_rating", lambda _: pytest.fail("domestic pacing rule was used"))
    segments = reporter.analyze_pacing()
    assert segments[0]["count_unit"] == "words"
    section = "\n".join(reporter._generate_pacing_section())
    assert "10 词" in section
    assert "字/爽点" not in section


@pytest.mark.parametrize("explicit", [False, True])
def test_unreadable_manuscript_is_not_reported_as_successful_zero_count(tmp_path, monkeypatch, explicit):
    if explicit:
        path = _project(tmp_path)
    else:
        (tmp_path / "正文").mkdir()
        path = tmp_path / "正文" / "第0001章.md"
        path.write_text("旧正文", encoding="utf-8")
    original_read_text = Path.read_text
    def denied(manuscript, *args, **kwargs):
        if manuscript == path:
            raise PermissionError("manuscript is locked")
        return original_read_text(manuscript, *args, **kwargs)
    monkeypatch.setattr(Path, "read_text", denied)
    if explicit:
        with pytest.raises(PermissionError, match="locked"):
            chapter_measurement(tmp_path, 1)
    else:
        assert chapter_measurement(tmp_path, 1)["word_count"] == 0


@pytest.mark.parametrize("clear_state_projection", [False, True])
def test_unaccepted_edit_does_not_change_total_until_that_chapter_is_replayed(tmp_path, clear_state_projection):
    manuscript = _project(tmp_path)
    service = ChapterCommitService(tmp_path)
    first = _commit(tmp_path)
    service.apply_projections(first)
    if clear_state_projection:
        state_path = tmp_path / ".webnovel" / "state.json"
        partial = json.loads(state_path.read_text(encoding="utf-8"))
        partial.pop("chapter_meta")
        state_path.write_text(json.dumps(partial), encoding="utf-8")
    manuscript.write_text("Only two.", encoding="utf-8")
    (tmp_path / "正文" / "第0002章.md").write_text(SAMPLE, encoding="utf-8")
    _seed_contracts(tmp_path, chapter=2)
    service.apply_projections(_commit(tmp_path, chapter=2))

    def assert_projected_total(expected):
        state = json.loads((tmp_path / ".webnovel" / "state.json").read_text(encoding="utf-8"))
        index = IndexManager(DataModulesConfig.from_project_root(tmp_path))
        assert state["progress"]["total_words"] == expected
        assert sum(index.get_chapter(chapter)["word_count"] for chapter in (1, 2)) == expected
        paths = StoryContractPaths.from_project_root(tmp_path)
        assert sum(json.loads(paths.commit_json(chapter).read_text(encoding="utf-8"))["extraction_result"]["chapter_meta"]["word_count"] for chapter in (1, 2)) == expected
    assert_projected_total(20)
    for _ in range(2):
        service.apply_projection_writers(first)
        assert_projected_total(12)


@pytest.mark.parametrize("layer", ["master", "volume", "chapter", "review"])
def test_stale_existing_contract_blocks_accepted_build_and_apply_before_events(tmp_path, layer):
    _project(tmp_path)
    payload = _commit(tmp_path)
    paths = StoryContractPaths.from_project_root(tmp_path)
    selected = {"master": paths.master_json, "volume": paths.volume_json(1),
                "chapter": paths.chapter_json(1), "review": paths.review_json(1)}[layer]
    contract = json.loads(selected.read_text(encoding="utf-8"))
    contract["meta"]["writing_profile_ref"]["sha256"] = "stale"
    selected.write_text(json.dumps(contract), encoding="utf-8")
    state_before = (tmp_path / ".webnovel" / "state.json").read_bytes()
    with pytest.raises(ValueError, match="stale"):
        _commit(tmp_path)
    service = ChapterCommitService(tmp_path)
    for apply in (service.apply_projections, service.apply_projection_writers):
        with pytest.raises(ValueError, match="stale"):
            apply(payload)
    assert not paths.event_json(1).exists()
    assert not paths.commit_json(1).exists()
    assert (tmp_path / ".webnovel" / "state.json").read_bytes() == state_before


def test_explicit_accepted_commit_requires_all_contract_bindings(tmp_path):
    _project(tmp_path)
    payload = _commit(tmp_path)
    paths = StoryContractPaths.from_project_root(tmp_path)
    for path in (paths.master_json, paths.volume_json(1), paths.chapter_json(1), paths.review_json(1)):
        path.unlink()
    with pytest.raises(ValueError, match="missing contract"):
        _commit(tmp_path)
    with pytest.raises(ValueError, match="missing contract"):
        ChapterCommitService(tmp_path).apply_projections(payload)
    assert not paths.event_json(1).exists()


def test_stale_commit_snapshot_cannot_replay_against_current_contracts(tmp_path):
    _project(tmp_path)
    payload = _commit(tmp_path)
    payload["meta"]["writing_profile_ref"] = {"sha256": "stale"}
    with pytest.raises(ValueError, match="stale"):
        ChapterCommitService(tmp_path).apply_projections(payload)
    assert not StoryContractPaths.from_project_root(tmp_path).event_json(1).exists()


def test_queued_explicit_commit_cannot_downgrade_when_other_markers_are_deleted(tmp_path):
    _project(tmp_path)
    payload = _commit(tmp_path)
    paths = StoryContractPaths.from_project_root(tmp_path)
    for path in (paths.master_json, paths.volume_json(1), paths.chapter_json(1), paths.review_json(1),
                 tmp_path / ".story-system" / "WRITING_PROFILE.json"):
        path.unlink()
    (tmp_path / ".webnovel" / "state.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="WRITING_PROFILE"):
        ChapterCommitService(tmp_path).apply_projections(payload)
    assert not paths.event_json(1).exists()


def test_partial_state_can_recover_accepted_measurement_from_existing_index(tmp_path):
    manuscript = _project(tmp_path)
    service = ChapterCommitService(tmp_path)
    first = _commit(tmp_path)
    service.apply_projections(first)
    paths = StoryContractPaths.from_project_root(tmp_path)
    paths.commit_json(1).unlink()
    state_path = tmp_path / ".webnovel" / "state.json"
    partial = json.loads(state_path.read_text(encoding="utf-8"))
    partial.pop("chapter_meta")
    state_path.write_text(json.dumps(partial), encoding="utf-8")
    manuscript.write_text("Only two.", encoding="utf-8")
    (tmp_path / "正文" / "第0002章.md").write_text(SAMPLE, encoding="utf-8")
    _seed_contracts(tmp_path, chapter=2)
    service.apply_projections(_commit(tmp_path, chapter=2))
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["progress"]["total_words"] == 20


def test_draft_metadata_cannot_replace_prior_accepted_measurement(tmp_path):
    manuscript = _project(tmp_path)
    service = ChapterCommitService(tmp_path)
    service.apply_projections(_commit(tmp_path))
    state_path = tmp_path / ".webnovel" / "state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["chapter_meta"]["0001"] = {"word_count": 2, "count_unit": "words"}
    state_path.write_text(json.dumps(state), encoding="utf-8")
    manuscript.write_text("Only two.", encoding="utf-8")
    (tmp_path / "正文" / "第0002章.md").write_text(SAMPLE, encoding="utf-8")
    _seed_contracts(tmp_path, chapter=2)
    service.apply_projections(_commit(tmp_path, chapter=2))
    assert json.loads(state_path.read_text(encoding="utf-8"))["progress"]["total_words"] == 20
