"""Market and profile boundaries at the writing runtime, using real contracts."""
import csv
import json

import pytest

from data_modules.story_contract_schema import MasterSetting
from data_modules.story_contracts import persist_story_seed
from reference_search import search


def _write(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _references(tmp_path):
    headers = ["编号", "适用技能", "适用题材", "关键词", "核心摘要", "market", "human_reviewed"]
    rows = [
        ["old", "write", "全部", "trial", "domestic legacy", "", ""],
        ["domestic", "write", "全部", "trial", "domestic explicit", "domestic", ""],
        ["foreign", "write", "全部", "trial", "overseas explicit", "overseas", ""],
        ["unreviewed", "write", "全部", "trial", "shared unreviewed", "shared", "false"],
        ["reviewed", "write", "全部", "trial", "shared reviewed", "shared", "true"],
    ]
    with (tmp_path / "场景写法.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(headers)
        writer.writerows(rows)
    return tmp_path


def test_reference_search_defaults_old_all_rows_to_domestic(tmp_path):
    result = search(_references(tmp_path), skill="write", query="trial", max_results=10)
    assert {row["编号"] for row in result["data"]["results"]} == {"old", "domestic", "reviewed"}


def test_reference_search_overseas_only_sees_own_and_reviewed_shared_rows(tmp_path):
    result = search(_references(tmp_path), skill="write", query="trial", market="overseas", max_results=10)
    assert {row["编号"] for row in result["data"]["results"]} == {"foreign", "reviewed"}


def test_contract_schema_keeps_profile_reference_for_runtime_children():
    master = MasterSetting.model_validate({"meta": {
        "contract_type": "MASTER_SETTING", "writing_profile_ref": {"path": ".story-system/WRITING_PROFILE.json", "sha256": "fixed"},
        "rule_pack_versions": {"litrpg": "1.0.0"}, "language_pack_version": "1.0.0", "market": "overseas", "body_language": "en",
    }})
    assert master.model_dump()["meta"]["writing_profile_ref"]["sha256"] == "fixed"
    assert master.model_dump()["meta"]["rule_pack_versions"] == {"litrpg": "1.0.0"}


def test_master_refresh_preserves_initialized_constraints_and_manual_values(tmp_path):
    old = {"meta": {"contract_type": "MASTER_SETTING"}, "route": {"primary_genre": "玄幻"},
           "master_constraints": {"core_tone": "quiet", "chapter_length": 2100, "pov": "close third"}, "author_notes": ["keep me"]}
    _write(tmp_path / ".story-system" / "MASTER_SETTING.json", old)
    persist_story_seed(tmp_path, {"meta": {"contract_type": "MASTER_SETTING"}, "route": {"primary_genre": "玄幻"}, "master_constraints": {"core_tone": "loud"}}, None, [])
    refreshed = json.loads((tmp_path / ".story-system" / "MASTER_SETTING.json").read_text(encoding="utf-8"))
    assert refreshed["author_notes"] == ["keep me"]
    assert refreshed["master_constraints"] == {"core_tone": "quiet", "chapter_length": 2100, "pov": "close third"}


def test_generated_markdown_preserves_existing_unmarked_author_notes(tmp_path):
    from data_modules.story_contracts import write_marked_markdown

    target = tmp_path / "MASTER_SETTING.md"
    target.write_text("# Author notes\nKeep the quiet tone.\n", encoding="utf-8")
    write_marked_markdown(target, "# Generated constraints\n")
    assert target.read_text(encoding="utf-8").startswith("# Author notes\nKeep the quiet tone.\n")
    assert "# Generated constraints" in target.read_text(encoding="utf-8")


def test_generated_markdown_rejects_damaged_markers_without_rewriting_notes(tmp_path):
    from data_modules.story_contracts import write_marked_markdown

    target = tmp_path / "MASTER_SETTING.md"
    original = "# Author notes\n<!-- STORY-SYSTEM:BEGIN -->\nHalf-written block\n"
    target.write_text(original, encoding="utf-8")
    with pytest.raises(ValueError):
        write_marked_markdown(target, "new generated block")
    assert target.read_text(encoding="utf-8") == original


def test_legacy_context_retains_all_secondary_genres(tmp_path):
    from data_modules.config import DataModulesConfig
    from data_modules.context_manager import ContextManager

    config = DataModulesConfig.from_project_root(tmp_path)
    config.ensure_dirs()
    manager = ContextManager(config)
    result = manager._load_genre_profile({"project": {"genre": "玄幻+悬疑+都市+历史"}})
    assert len(result["genres"]) == 4
    assert len(result["secondary_genres"]) == 3


@pytest.fixture
def foreign_project(tmp_path):
    from data_modules.writing_profile import build_writing_profile, save_writing_profile

    profile = build_writing_profile(market="overseas", body_language="en", genre="progression_fantasy", secondary_genres=["litrpg", "romantasy"], allow_draft_rules=True)
    _write(tmp_path / ".webnovel" / "state.json", {"writing_profile": profile.to_snapshot(), "progress": {}})
    save_writing_profile(tmp_path, profile)
    return tmp_path, profile


def _seed_foreign(root, profile, chapter=1):
    from data_modules.story_system_engine import StorySystemEngine
    from data_modules.runtime_contract_builder import RuntimeContractBuilder
    from data_modules.story_contracts import persist_runtime_contracts

    contract = StorySystemEngine(root / "unused-csv", writing_profile=profile).build("Mira earns a skill", None, chapter)
    persist_story_seed(root, contract["master_setting"], contract["chapter_brief"], contract["anti_patterns"])
    volume, review = RuntimeContractBuilder(root).build_for_chapter(chapter)
    persist_runtime_contracts(root, chapter, volume, review)
    return contract, volume, review


def test_foreign_engine_never_uses_domestic_csv_and_children_keep_profile(foreign_project):
    root, profile = foreign_project
    contract, volume, review = _seed_foreign(root, profile)
    assert contract["master_setting"]["route"]["secondary_genres"] == ["litrpg", "romantasy"]
    assert contract["master_setting"]["route"]["market"] == "overseas"
    for payload in (contract["master_setting"], contract["chapter_brief"], volume, review):
        assert payload["meta"]["writing_profile_ref"] == profile.reference()
        assert payload["meta"]["rule_pack_versions"] == profile.rule_pack_versions
    assert "language_advisory" in review
    assert "language_advisory" not in review["blocking_rules"]


def test_engine_rejects_changed_secondary_order_instead_of_silently_ignoring_it(foreign_project):
    from data_modules.story_system_engine import StorySystemEngine

    root, profile = foreign_project
    with pytest.raises(ValueError, match="conflicts"):
        StorySystemEngine(root / "unused", writing_profile=profile).build("training", "progression_fantasy+romantasy+litrpg", 1)


def test_foreign_context_preserves_profile_and_excludes_legacy_guidance(foreign_project):
    from data_modules.config import DataModulesConfig
    from data_modules.context_manager import ContextManager

    root, profile = foreign_project
    _seed_foreign(root, profile)
    manager = ContextManager(DataModulesConfig.from_project_root(root))
    payload = manager.build_context(1)
    assert payload["genre_profile"]["genres"] == ["progression_fantasy", "litrpg", "romantasy"]
    assert payload["genre_profile"]["body_language"] == "en"
    assert payload["writing_guidance"]["language_rules"]["body_language"] == "en"
    assert payload["prewrite_validation"]["blocking"] is False
    assert "shuangwen" not in json.dumps(payload, ensure_ascii=False)
    assert not payload["writing_guidance"].get("methodology")


@pytest.mark.parametrize("damage", ["missing_ref", "stale_fingerprint", "wrong_pack_version"])
def test_prewrite_blocks_stale_or_unbound_profile_contracts(foreign_project, damage):
    from data_modules.prewrite_validator import PrewriteValidator

    root, profile = foreign_project
    contract, volume, review = _seed_foreign(root, profile)
    story = {"master_setting": contract["master_setting"], "chapter_brief": contract["chapter_brief"], "volume_brief": volume, "review_contract": review}
    meta = story["chapter_brief"]["meta"]
    if damage == "missing_ref":
        meta.pop("writing_profile_ref")
    elif damage == "stale_fingerprint":
        meta["writing_profile_ref"] = {**profile.reference(), "sha256": "outdated"}
    else:
        meta["rule_pack_versions"] = {"progression_fantasy": "0.0.0"}
    result = PrewriteValidator(root).build(1, review, {}, story)
    assert result["blocking"] is True
    assert result["writing_profile_errors"]


def test_runtime_rejects_removed_profile_instead_of_returning_domestic_context(foreign_project):
    from data_modules.story_runtime_sources import load_runtime_sources

    root, profile = foreign_project
    _seed_foreign(root, profile)
    (root / ".story-system" / "WRITING_PROFILE.json").unlink()
    with pytest.raises(ValueError):
        load_runtime_sources(root, 1)


def test_preflight_reports_stale_profile_as_failure(foreign_project):
    from data_modules.webnovel import _build_preflight_report

    root, profile = foreign_project
    _seed_foreign(root, profile)
    chapter_path = root / ".story-system" / "chapters" / "chapter_001.json"
    chapter = json.loads(chapter_path.read_text(encoding="utf-8"))
    chapter["meta"]["writing_profile_ref"]["sha256"] = "stale"
    _write(chapter_path, chapter)
    report = _build_preflight_report(str(root))
    assert report["ok"] is False
    assert any(check["name"] == "writing_profile_contracts" and not check["ok"] for check in report["checks"])


def test_prewrite_gate_returns_blocker_for_invalid_profile_contract(foreign_project):
    from data_modules.write_gates import run_write_gate

    root, profile = foreign_project
    _seed_foreign(root, profile)
    (root / ".story-system" / "WRITING_PROFILE.json").unlink()
    report = run_write_gate(root, chapter=1, stage="prewrite")
    assert report["ok"] is False
    assert any(item["code"] == "writing_profile_contracts_invalid" for item in report["errors"])


def test_runtime_rejects_invalid_contract_shape_as_profile_error(foreign_project):
    from data_modules.story_runtime_sources import load_runtime_sources

    root, profile = foreign_project
    _seed_foreign(root, profile)
    _write(root / ".story-system" / "chapters" / "chapter_001.json", {"meta": ["broken"]})
    with pytest.raises(ValueError, match="chapter"):
        load_runtime_sources(root, 1)


def test_repeated_legacy_cli_generation_keeps_project_usable_without_profile(tmp_path, monkeypatch, capsys):
    import sys
    from story_system import main
    from data_modules.writing_profile import load_writing_profile

    _write(tmp_path / ".webnovel" / "state.json", {"project": {"genre": "玄幻"}})
    for _ in range(2):
        monkeypatch.setattr(sys, "argv", ["story_system", "玄幻退婚流", "--project-root", str(tmp_path), "--chapter", "1", "--persist", "--emit-runtime-contracts"])
        main()
        capsys.readouterr()
    assert not (tmp_path / ".story-system" / "WRITING_PROFILE.json").exists()
    assert load_writing_profile(tmp_path).reference()["legacy"] is True


@pytest.mark.parametrize("kind", ["chapter", "volume", "review"])
def test_child_refresh_preserves_author_overrides_and_replaces_generated_fields(foreign_project, kind):
    from data_modules.story_contracts import StoryContractPaths

    root, profile = foreign_project
    _seed_foreign(root, profile)
    paths = StoryContractPaths.from_project_root(root)
    path = {"chapter": paths.chapter_json(1), "volume": paths.volume_json(1), "review": paths.review_json(1)}[kind]
    existing = json.loads(path.read_text(encoding="utf-8"))
    if kind == "chapter":
        existing["override_allowed"]["author_constraint"] = "Mira keeps her alias secret"
        existing["chapter_directive"] = {"goal": "old generated outline"}
    elif kind == "volume":
        existing["overrides"]["locked"]["pov"] = "close third"
        existing["selected_scenes"] = ["old generated scene"]
    else:
        existing["overrides"]["append_only"]["author_constraints"] = ["Preserve the established oath"]
        existing["must_check"] = ["old generated review node"]
    _write(path, existing)

    _seed_foreign(root, profile)

    refreshed = json.loads(path.read_text(encoding="utf-8"))
    if kind == "chapter":
        assert refreshed["override_allowed"]["author_constraint"] == "Mira keeps her alias secret"
        assert refreshed["chapter_directive"] == {}
    elif kind == "volume":
        assert refreshed["overrides"]["locked"]["pov"] == "close third"
        assert refreshed["selected_scenes"] == []
    else:
        assert refreshed["overrides"]["append_only"]["author_constraints"] == ["Preserve the established oath"]
        assert refreshed["must_check"] == []


def test_runtime_refresh_merges_append_only_and_keeps_author_editable_values(foreign_project):
    from copy import deepcopy
    from data_modules.story_contracts import StoryContractPaths, persist_runtime_contracts

    root, profile = foreign_project
    _, volume, review = _seed_foreign(root, profile)
    volume["overrides"]["override_allowed"] = {"scene_focus": "author's focus"}
    review["overrides"]["append_only"] = {"constraints": ["oath", "identity"]}
    persist_runtime_contracts(root, 1, volume, review)
    regenerated_volume, regenerated_review = deepcopy(volume), deepcopy(review)
    regenerated_volume["overrides"]["override_allowed"] = {"scene_focus": "generated focus", "weather": "rain"}
    regenerated_review["overrides"]["append_only"] = {"constraints": ["identity", "timeline"]}
    persist_runtime_contracts(root, 1, regenerated_volume, regenerated_review)
    paths = StoryContractPaths.from_project_root(root)
    assert json.loads(paths.volume_json(1).read_text(encoding="utf-8"))["overrides"]["override_allowed"] == {"scene_focus": "author's focus", "weather": "rain"}
    assert json.loads(paths.review_json(1).read_text(encoding="utf-8"))["overrides"]["append_only"] == {"constraints": ["oath", "identity", "timeline"]}


@pytest.mark.parametrize("conflict", ["profile", "locked"])
def test_runtime_refresh_rejects_conflict_before_writing_either_child(foreign_project, conflict):
    from copy import deepcopy
    from data_modules.story_contracts import StoryContractPaths, persist_runtime_contracts

    root, profile = foreign_project
    _, volume, review = _seed_foreign(root, profile)
    volume["overrides"]["locked"] = {"pov": "close third"}
    persist_runtime_contracts(root, 1, volume, review)
    paths = StoryContractPaths.from_project_root(root)
    before = [path.read_bytes() for path in (paths.volume_json(1), paths.review_json(1))]
    regenerated_volume, regenerated_review = deepcopy(volume), deepcopy(review)
    if conflict == "profile":
        regenerated_review["meta"]["writing_profile_ref"]["sha256"] = "other profile"
    else:
        regenerated_volume["overrides"]["locked"]["pov"] = "omniscient"
    with pytest.raises(ValueError, match="conflict"):
        persist_runtime_contracts(root, 1, regenerated_volume, regenerated_review)
    assert [path.read_bytes() for path in (paths.volume_json(1), paths.review_json(1))] == before


def test_chapter_refresh_rejects_profile_mismatch_before_rewriting_master(foreign_project):
    from data_modules.story_contracts import StoryContractPaths

    root, profile = foreign_project
    _seed_foreign(root, profile)
    paths = StoryContractPaths.from_project_root(root)
    chapter = json.loads(paths.chapter_json(1).read_text(encoding="utf-8"))
    chapter["meta"]["writing_profile_ref"]["sha256"] = "other profile"
    _write(paths.chapter_json(1), chapter)
    before = paths.master_json.read_bytes()
    with pytest.raises(ValueError, match="conflict"):
        _seed_foreign(root, profile)
    assert paths.master_json.read_bytes() == before
