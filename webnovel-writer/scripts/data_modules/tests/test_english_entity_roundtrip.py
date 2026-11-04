"""Names and machine identifiers survive the same commit and projection chain."""
import json

from data_modules.chapter_commit_service import ChapterCommitService
from data_modules.config import DataModulesConfig
from data_modules.index_manager import IndexManager
from data_modules.profile_contracts import profile_meta
from data_modules.story_contracts import StoryContractPaths, write_json
from data_modules.writing_profile import build_writing_profile, save_writing_profile


def test_english_names_aliases_and_machine_fields_survive_replay(tmp_path):
    profile = build_writing_profile(market="overseas", body_language="en", genre="litrpg", allow_draft_rules=True)
    save_writing_profile(tmp_path, profile)
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
    (tmp_path / "正文").mkdir()
    (tmp_path / "正文/第0001章.md").write_text("Maeve unlocked Bridge-Sense.", encoding="utf-8")
    service = ChapterCommitService(tmp_path)
    commit = service.build_commit(1, {"blocking_count": 0},
                                  {"planned_nodes": [], "covered_nodes": [], "missed_nodes": [], "extra_nodes": []},
                                  {"pending": []}, {
        "accepted_events": [], "state_deltas": [{"entity_id": "maeve_oconnell", "field": "skill_points", "new": 7}],
        "entity_deltas": [{"entity_id": "maeve_oconnell", "canonical_name": "Maeve O’Connell", "entity_type": "角色",
                           "aliases": ["Maeve", "Bridge-Keeper", "M. O’Connell"], "is_protagonist": True,
                           "current": {"skill_id": "bridge_sense_v2", "ui_label": "Bridge-Sense", "skill_points": 7}}],
        "entities_appeared": [{"id": "maeve_oconnell", "mentions": ["Maeve", "M. O’Connell"], "confidence": 1.0}],
    })
    for _ in range(2):
        assert service.apply_projections(commit)["projection_status"]["index"] == "done"
    stored = json.loads((tmp_path / ".story-system/commits/chapter_001.commit.json").read_text(encoding="utf-8"))
    assert stored["extraction_result"]["entity_deltas"][0]["aliases"] == ["Maeve", "Bridge-Keeper", "M. O’Connell"]
    manager = IndexManager(DataModulesConfig.from_project_root(tmp_path))
    entity = manager.get_entity("Bridge-Keeper")
    assert entity is not None
    assert entity["id"] == "maeve_oconnell"
    assert entity["canonical_name"] == "Maeve O’Connell"
    assert entity["current_json"]["skill_id"] == "bridge_sense_v2"
    aliases = manager.get_entity_aliases("maeve_oconnell")
    assert all(aliases.count(value) == 1 for value in ["Maeve", "Bridge-Keeper", "M. O’Connell"])
    state = json.loads((tmp_path / ".webnovel/state.json").read_text(encoding="utf-8"))
    assert state["entity_state"]["maeve_oconnell"]["skill_points"] == 7
