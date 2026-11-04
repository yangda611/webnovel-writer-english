"""Editorial advice reaches consumers without becoming another fact gate."""
import json
from pathlib import Path

import pytest

from data_modules.config import DataModulesConfig
from data_modules.context_manager import ContextManager
from data_modules.runtime_contract_builder import RuntimeContractBuilder
from data_modules.story_contract_schema import ChapterBrief, MasterSetting
from data_modules.story_contracts import persist_story_seed, persist_runtime_contracts
from data_modules.story_system_engine import StorySystemEngine
from data_modules.writing_profile import build_writing_profile, save_writing_profile


@pytest.mark.parametrize("language", ["zh", "en"])
def test_all_contracts_and_context_keep_primary_secondary_roles(tmp_path, language):
    profile = build_writing_profile(market="overseas", body_language=language,
                                    genre="litrpg+romantasy+progression_fantasy", allow_draft_rules=True)
    save_writing_profile(tmp_path, profile)
    state = tmp_path / ".webnovel/state.json"
    state.parent.mkdir()
    state.write_text(json.dumps({"project_info": {"writing_profile": profile.to_snapshot()}, "progress": {}}), encoding="utf-8")
    result = StorySystemEngine(tmp_path / "no-domestic-csv", writing_profile=profile).build(
        query="repair the lock", genre=None, chapter=1)
    chapter = ChapterBrief.model_validate(result["chapter_brief"]).model_dump()
    master = MasterSetting.model_validate(result["master_setting"]).model_dump()
    # Fails if generated prose rules are discarded by Pydantic (the old bug).
    assert chapter.get("language_rules", {}).get("body_language") == language
    expected = [("litrpg", "primary"), ("romantasy", "secondary"), ("progression_fantasy", "secondary")]
    for contract in (chapter, master):
        guidance = contract.get("editorial_guidance", {})
        assert [(g["genre"], g["role"]) for g in guidance.get("genre_roles", [])] == expected
        assert guidance["advisory_only"] is True
        assert guidance["genre_roles"][0]["continuity_ledger"]
        assert guidance["genre_roles"][1]["secondary_application"]
    persist_story_seed(tmp_path, result["master_setting"], result["chapter_brief"], [])
    volume, review = RuntimeContractBuilder(tmp_path).build_for_chapter(1)
    persist_runtime_contracts(tmp_path, 1, volume, review)
    for contract in (volume, review):
        guidance = contract.get("editorial_guidance", {})
        assert [(g["genre"], g["role"]) for g in guidance.get("genre_roles", [])] == expected
        assert guidance["language"]["body_language"] == language
    assert review["blocking_rules"] == []
    assert review["must_check"] == []
    context = ContextManager(DataModulesConfig.from_project_root(tmp_path)).build_context(1)
    assert context["writing_guidance"]["editorial_guidance"]["genre_roles"][1]["role"] == "secondary"
    assert context["prewrite_validation"]["blocking"] is False
    assert "shuangwen" not in json.dumps(context, ensure_ascii=False)


def test_legacy_editorial_fields_remain_empty(tmp_path):
    csv_dir = Path(__file__).resolve().parents[3] / "references/csv"
    result = StorySystemEngine(csv_dir).build("调查", genre="悬疑", chapter=1)
    chapter = ChapterBrief.model_validate(result["chapter_brief"]).model_dump()
    assert chapter.get("editorial_guidance") == {}


def test_changing_language_preserves_genre_editorial_instructions(tmp_path):
    guidance = []
    for language in ("zh", "en"):
        profile = build_writing_profile(market="overseas", body_language=language,
                                        genre="progression_fantasy+litrpg", allow_draft_rules=True)
        result = StorySystemEngine(tmp_path / "missing", writing_profile=profile).build("learn", genre=None, chapter=2)
        guidance.append(result["chapter_brief"].get("editorial_guidance", {}))
    assert guidance[0].get("genre_roles")
    assert guidance[0]["genre_roles"] == guidance[1]["genre_roles"]
    assert guidance[0]["language"]["body_language"] == "zh"
    assert guidance[1]["language"]["body_language"] == "en"
