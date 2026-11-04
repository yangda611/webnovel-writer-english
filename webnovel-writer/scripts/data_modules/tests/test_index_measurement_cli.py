"""Public index writes cannot label an imported character count as English words."""

import json
import sys

import pytest

from data_modules import index_manager as index_module
from data_modules.config import DataModulesConfig
from data_modules.index_manager import ChapterMeta, IndexManager
from data_modules.writing_profile import build_writing_profile, save_writing_profile


SAMPLE = "The old bridge crossed the river beneath a pale sky."


def _project(root, market="overseas", language="en"):
    profile = build_writing_profile(
        market=market, body_language=language,
        genre="仙侠" if market == "domestic" else "progression_fantasy",
        allow_draft_rules=True,
    )
    save_writing_profile(root, profile)
    (root / ".webnovel").mkdir(exist_ok=True)
    (root / ".webnovel" / "state.json").write_text(
        json.dumps({"writing_profile": profile.to_snapshot()}), encoding="utf-8"
    )
    (root / "正文").mkdir()
    path = root / "正文" / "第0001章.md"
    path.write_text(f"# Chapter One\n\n{SAMPLE}", encoding="utf-8")
    return path


def _cli(root, monkeypatch, capsys, *args):
    monkeypatch.setattr(sys, "argv", ["index_manager", "--project-root", str(root), *args])
    index_module.main()
    return json.loads(capsys.readouterr().out)


def _process(root, monkeypatch, capsys):
    return _cli(root, monkeypatch, capsys, "process-chapter", "--chapter", "1",
        "--title", "A New Bridge", "--location", "River Gate", "--word-count", "9999",
        "--entities", "[]", "--scenes", "[]")


@pytest.mark.parametrize("market,language,count,unit", [
    ("domestic", "zh", 52, "characters"), ("overseas", "zh", 52, "characters"),
    ("overseas", "en", 10, "words"),
])
def test_public_cli_recounts_manuscript_with_profile_unit(tmp_path, monkeypatch, capsys, market, language, count, unit):
    path = _project(tmp_path, market, language)
    assert _process(tmp_path, monkeypatch, capsys)["status"] == "success"
    chapter = _cli(tmp_path, monkeypatch, capsys, "get-chapter", "--chapter", "1")["data"]
    assert (chapter["word_count"], chapter["count_unit"]) == (count, unit)
    path.write_text("Only two.", encoding="utf-8")
    _process(tmp_path, monkeypatch, capsys)
    chapter = _cli(tmp_path, monkeypatch, capsys, "get-chapter", "--chapter", "1")["data"]
    assert chapter["word_count"] == (2 if language == "en" else 9)
    assert chapter["count_unit"] == unit


@pytest.mark.parametrize("failure", ["missing_profile", "corrupt_profile", "missing_manuscript"])
def test_public_cli_measurement_failure_preserves_prior_chapter(tmp_path, monkeypatch, capsys, failure):
    path = _project(tmp_path)
    _process(tmp_path, monkeypatch, capsys)
    profile_file = tmp_path / ".story-system" / "WRITING_PROFILE.json"
    if failure == "missing_profile":
        profile_file.unlink()
    elif failure == "corrupt_profile":
        profile_file.write_text("{broken", encoding="utf-8")
    else:
        path.unlink()
    result = _process(tmp_path, monkeypatch, capsys)
    assert result["status"] == "error"
    assert result["error"]["code"] == "INVALID_CHAPTER_MEASUREMENT"
    chapter = IndexManager(DataModulesConfig.from_project_root(tmp_path)).get_chapter(1)
    assert (chapter["word_count"], chapter["count_unit"]) == (10, "words")


def test_direct_public_index_api_recounts_and_rejects_missing_profile(tmp_path):
    _project(tmp_path)
    manager = IndexManager(DataModulesConfig.from_project_root(tmp_path))
    manager.add_chapter(ChapterMeta(1, "Bridge", "River", 9999, [], count_unit="characters"))
    chapter = manager.get_chapter(1)
    assert (chapter["word_count"], chapter["count_unit"]) == (10, "words")
    (tmp_path / ".story-system" / "WRITING_PROFILE.json").unlink()
    with pytest.raises(ValueError, match="WRITING_PROFILE"):
        manager.add_chapter(ChapterMeta(1, "Overwrite", "", 9999, []))
    assert manager.get_chapter(1)["title"] == "Bridge"


def test_legacy_public_index_api_keeps_imported_numeric_count(tmp_path):
    manager = IndexManager(DataModulesConfig.from_project_root(tmp_path))
    manager.add_chapter(ChapterMeta(1, "旧章", "旧地点", 123, []))
    chapter = manager.get_chapter(1)
    assert (chapter["word_count"], chapter["count_unit"]) == (123, "characters")


def test_english_character_aliases_and_machine_state_survive_public_cli(tmp_path, monkeypatch, capsys):
    _project(tmp_path)
    missing = _cli(tmp_path, monkeypatch, capsys, "get-protagonist")
    assert missing["error"]["code"] == "NOT_FOUND"
    hero = {"id": "rowan_oneil", "type": "角色", "canonical_name": "Rowan O’Neil",
            "is_protagonist": True, "current": {"stats": {"level": 42}}}
    assert _cli(tmp_path, monkeypatch, capsys, "upsert-entity", "--data", json.dumps(hero))["status"] == "success"
    stored = _cli(tmp_path, monkeypatch, capsys, "get-protagonist")["data"]
    assert (stored["id"], stored["canonical_name"]) == ("rowan_oneil", "Rowan O’Neil")
    assert stored["current_json"]["stats"]["level"] == 42
    assert _cli(tmp_path, monkeypatch, capsys, "get-aliases", "--entity", "missing")["error"]["code"] == "NOT_FOUND"
    alias_args = ("register-alias", "--alias", "The Bridge-Walker", "--entity", "rowan_oneil", "--type", "角色")
    assert _cli(tmp_path, monkeypatch, capsys, *alias_args)["status"] == "success"
    assert _cli(tmp_path, monkeypatch, capsys, *alias_args)["error"]["code"] == "ALIAS_EXISTS"
    resolved = _cli(tmp_path, monkeypatch, capsys, "get-by-alias", "--alias", "The Bridge-Walker")
    assert resolved["data"][0]["canonical_name"] == "Rowan O’Neil"
    aliases = _cli(tmp_path, monkeypatch, capsys, "get-aliases", "--entity", "rowan_oneil")["data"]["aliases"]
    assert "The Bridge-Walker" in aliases
    assert _cli(tmp_path, monkeypatch, capsys, "get-by-alias", "--alias", "Unknown")["error"]["code"] == "NOT_FOUND"
    change = {"entity_id": "rowan_oneil", "field": "stats.level", "old_value": "41",
              "new_value": "42", "chapter": 1, "reason": "Bridge trial"}
    assert _cli(tmp_path, monkeypatch, capsys, "record-state-change", "--data", json.dumps(change))["status"] == "success"
    changes = _cli(tmp_path, monkeypatch, capsys, "get-state-changes", "--entity", "rowan_oneil")["data"]
    assert (changes[0]["field"], changes[0]["new_value"]) == ("stats.level", "42")


def test_public_cli_invalid_relationship_event_cannot_write_fact(tmp_path, monkeypatch, capsys):
    _project(tmp_path)
    for raw in ("{broken", json.dumps({"from_entity": "", "to_entity": "", "type": "ally", "chapter": 1})):
        result = _cli(tmp_path, monkeypatch, capsys, "record-relationship-event", "--data", raw)
        assert result["error"]["code"] == "INVALID_RELATIONSHIP_EVENT"
    events = _cli(tmp_path, monkeypatch, capsys, "get-relationship-events", "--entity", "rowan_oneil")["data"]
    assert events == []
