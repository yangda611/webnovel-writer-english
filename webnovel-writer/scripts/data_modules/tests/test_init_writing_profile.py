import json

import pytest

import init_project
from data_modules.writing_profile import load_writing_profile


@pytest.fixture(autouse=True)
def no_git(monkeypatch):
    monkeypatch.setattr(init_project, "is_git_available", lambda: False)
    monkeypatch.setattr(init_project, "write_current_project_pointer", lambda root: None)


@pytest.mark.parametrize("market,language,genre", [
    ("domestic", "zh", "规则怪谈+悬疑"),
    ("overseas", "zh", "成长奇幻+LitRPG"),
    ("overseas", "en", "progression_fantasy+litrpg+romantasy"),
])
def test_init_three_combinations(tmp_path, market, language, genre):
    init_project.init_project(str(tmp_path), "桥之誓", genre, market=market, body_language=language,
                              protagonist_name="Maeve O’Connell", allow_draft_rules=True)
    profile = load_writing_profile(tmp_path)
    state = json.loads((tmp_path / ".webnovel/state.json").read_text(encoding="utf-8"))
    master = json.loads((tmp_path / ".story-system/MASTER_SETTING.json").read_text(encoding="utf-8"))
    assert state["project_info"]["writing_profile"] == profile.to_snapshot()
    assert master["meta"]["writing_profile_ref"] == profile.reference()
    assert state["protagonist_state"]["name"] == "Maeve O’Connell"
    assert state["project_info"]["secondary_genres"] == profile.secondary_genres
    assert (tmp_path / "正文").is_dir()
    if market == "overseas":
        rules = json.loads((tmp_path / "设定集/创作规则.md").read_text(encoding="utf-8").split("\n", 1)[1])
        assert all(pack["version"] == "1.1.0" and pack["status"] == "draft" for pack in rules["genre_rules"])
        assert (tmp_path / "大纲/题材承诺.md").is_file()
        all_settings = "\n".join(p.read_text(encoding="utf-8") for p in (tmp_path / "设定集").glob("*.md"))
        assert "突破境界" not in all_settings and "每章至少" not in all_settings
        assert "修仙" not in (tmp_path / "设定集/力量体系.md").read_text(encoding="utf-8")


def test_reinit_preserves_all_existing_files_and_config(tmp_path):
    kwargs = dict(market="overseas", body_language="en", allow_draft_rules=True, chapter_length=1700)
    init_project.init_project(str(tmp_path), "A Bridge", "litrpg", **kwargs)
    chapter = tmp_path / "正文/第0001章.md"
    chapter.write_text("The old bridge crossed the river beneath a pale sky.", encoding="utf-8")
    state_path = tmp_path / ".webnovel/state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["progress"]["current_chapter"] = 8
    state["progress"]["total_words"] = 10000
    state_path.write_text(json.dumps(state), encoding="utf-8")
    before = {p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    init_project.init_project(str(tmp_path), "A Bridge", "LitRPG", **kwargs)
    assert before == {p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}


def test_reinit_omitted_choices_keep_existing_and_conflict_fails(tmp_path):
    init_project.init_project(str(tmp_path), "A Bridge", "litrpg", market="overseas", body_language="en", allow_draft_rules=True)
    init_project.init_project(str(tmp_path), "A Bridge", "litrpg")
    assert load_writing_profile(tmp_path).body_language == "en"
    with pytest.raises(SystemExit, match="已有|不同|冲突"):
        init_project.init_project(str(tmp_path), "A Bridge", "litrpg", body_language="zh")
    assert load_writing_profile(tmp_path).body_language == "en"


def test_missing_foreign_profile_cannot_be_reinitialized_as_domestic(tmp_path):
    init_project.init_project(str(tmp_path), "A Bridge", "litrpg", market="overseas", allow_draft_rules=True)
    (tmp_path / ".story-system/WRITING_PROFILE.json").unlink()
    before = (tmp_path / ".webnovel/state.json").read_bytes()
    with pytest.raises(SystemExit, match="WRITING_PROFILE"):
        init_project.init_project(str(tmp_path), "别的书", "仙侠")
    assert (tmp_path / ".webnovel/state.json").read_bytes() == before


def test_invalid_secondary_init_has_no_files(tmp_path):
    path = tmp_path / "book"
    with pytest.raises(SystemExit, match="neverland"):
        init_project.init_project(str(path), "New", "litrpg+neverland", market="overseas", allow_draft_rules=True)
    assert not path.exists()


def test_reinit_legacy_project_is_readonly(tmp_path):
    state_dir = tmp_path / ".webnovel"
    state_dir.mkdir()
    payload = {"project_info": {"title": "旧书", "genre": "仙侠"}, "progress": {"current_chapter": 80}}
    path = state_dir / "state.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    init_project.init_project(str(tmp_path), "旧书", "仙侠")
    assert json.loads(path.read_text(encoding="utf-8")) == payload
    assert not (tmp_path / ".story-system/WRITING_PROFILE.json").exists()


def test_reinit_with_only_primary_preserves_saved_secondary_choices(tmp_path):
    init_project.init_project(str(tmp_path), "Bridge", "litrpg", market="overseas", body_language="en",
                              secondary_genres=["romantasy", "成长奇幻"], allow_draft_rules=True)
    before = load_writing_profile(tmp_path).reference()
    init_project.init_project(str(tmp_path), "Bridge", "LitRPG")
    assert load_writing_profile(tmp_path).reference() == before


def test_reinit_recognizes_legacy_project_container_and_cannot_change_market(tmp_path):
    state = tmp_path / ".webnovel/state.json"
    state.parent.mkdir()
    state.write_text(json.dumps({"project": {"title": "旧书", "genre": "仙侠"},
                                  "progress": {"current_chapter": 50, "total_words": 100000}}), encoding="utf-8")
    (tmp_path / "正文").mkdir()
    (tmp_path / "正文/第0050章.md").write_text("旧正文，不可换单位。", encoding="utf-8")
    before = {p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    with pytest.raises(SystemExit, match="已有"):
        init_project.init_project(str(tmp_path), "New", "litrpg", market="overseas", body_language="en", allow_draft_rules=True)
    init_project.init_project(str(tmp_path), "旧书", "仙侠")
    assert before == {p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}


def test_partial_legacy_project_with_manuscript_is_not_silently_reinitialized(tmp_path):
    (tmp_path / "正文").mkdir()
    (tmp_path / "正文/第0001章.md").write_text("旧正文，书名元信息已丢失。", encoding="utf-8")
    with pytest.raises(SystemExit, match="已有正文"):
        init_project.init_project(str(tmp_path), "New", "litrpg", market="overseas", body_language="en", allow_draft_rules=True)
    assert not (tmp_path / ".story-system/WRITING_PROFILE.json").exists()


def test_master_only_legacy_project_is_not_reinitialized_without_identity(tmp_path):
    master_path = tmp_path / ".story-system/MASTER_SETTING.json"
    master_path.parent.mkdir(parents=True)
    original = {"meta": {"contract_type": "MASTER_SETTING"},
                "route": {"primary_genre": "仙侠"},
                "master_constraints": {"core_tone": "保留作者设定"}}
    master_path.write_text(json.dumps(original, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(SystemExit, match="MASTER_SETTING.*书名|书名.*MASTER_SETTING"):
        init_project.init_project(str(tmp_path), "New", "litrpg", market="overseas", body_language="en",
                                  allow_draft_rules=True)

    assert json.loads(master_path.read_text(encoding="utf-8")) == original
    assert not (tmp_path / ".webnovel/state.json").exists()
    assert not (tmp_path / ".story-system/WRITING_PROFILE.json").exists()


@pytest.mark.parametrize("delete_master", [False, True])
def test_reinit_repairs_explicit_project_master_contract(tmp_path, delete_master):
    kwargs = dict(market="overseas", body_language="en", allow_draft_rules=True)
    init_project.init_project(str(tmp_path), "A Bridge", "litrpg", **kwargs)
    master_path = tmp_path / ".story-system/MASTER_SETTING.json"
    if delete_master:
        master_path.unlink()
    else:
        original = {"meta": {"contract_type": "MASTER_SETTING"},
                    "route": {"primary_genre": "author-authored-label"},
                    "master_constraints": {"core_tone": "保留作者设定"},
                    "author_data": {"keep": True}}
        master_path.write_text(json.dumps(original, ensure_ascii=False), encoding="utf-8")

    init_project.init_project(str(tmp_path), "A Bridge", "LitRPG")

    master = json.loads(master_path.read_text(encoding="utf-8"))
    from data_modules.profile_contracts import contract_profile_errors
    assert contract_profile_errors(tmp_path, {"MASTER_SETTING": master}) == []
    if not delete_master:
        assert master["master_constraints"]["core_tone"] == "保留作者设定"
        assert master["author_data"] == {"keep": True}


def test_interrupted_explicit_init_rejects_master_profile_conflict_before_writing(tmp_path):
    init_project.init_project(str(tmp_path), "A Bridge", "litrpg", market="overseas", body_language="en",
                              allow_draft_rules=True)
    profile_path = tmp_path / ".story-system/WRITING_PROFILE.json"
    state_path = tmp_path / ".webnovel/state.json"
    master_path = tmp_path / ".story-system/MASTER_SETTING.json"
    state_path.unlink()
    master = json.loads(master_path.read_text(encoding="utf-8"))
    master["meta"]["writing_profile_ref"]["sha256"] = "stale-reference"
    master_path.write_text(json.dumps(master, ensure_ascii=False), encoding="utf-8")
    before = {path: path.read_bytes() for path in (profile_path, master_path)}

    with pytest.raises(SystemExit, match="MASTER_SETTING.*conflict|MASTER_SETTING.*冲突|profile reference"):
        init_project.init_project(str(tmp_path), "A Bridge", "litrpg")

    assert before == {path: path.read_bytes() for path in (profile_path, master_path)}
    assert not state_path.exists()


def test_reinit_repairs_master_route_from_authoritative_profile(tmp_path):
    init_project.init_project(str(tmp_path), "A Bridge", "litrpg", market="overseas", body_language="en",
                              secondary_genres=["progression_fantasy"], allow_draft_rules=True)
    master_path = tmp_path / ".story-system/MASTER_SETTING.json"
    master = json.loads(master_path.read_text(encoding="utf-8"))
    master["route"].update({
        "primary_genre": "romantasy",
        "secondary_genres": [],
        "market": "domestic",
        "body_language": "zh",
        "author_note": "retain this route note",
    })
    master_path.write_text(json.dumps(master, ensure_ascii=False), encoding="utf-8")
    from data_modules.profile_contracts import contract_profile_errors
    assert contract_profile_errors(tmp_path, {"MASTER_SETTING": master})

    init_project.init_project(str(tmp_path), "A Bridge", "litrpg")

    repaired = json.loads(master_path.read_text(encoding="utf-8"))
    assert repaired["route"]["primary_genre"] == "litrpg"
    assert repaired["route"]["secondary_genres"] == ["progression_fantasy"]
    assert repaired["route"]["market"] == "overseas"
    assert repaired["route"]["body_language"] == "en"
    assert repaired["route"]["author_note"] == "retain this route note"
    assert repaired["master_constraints"]["writing_profile"] == load_writing_profile(tmp_path).to_snapshot()
    assert contract_profile_errors(tmp_path, {"MASTER_SETTING": repaired}) == []
