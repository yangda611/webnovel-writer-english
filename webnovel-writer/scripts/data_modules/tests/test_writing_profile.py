"""Project configuration is authoritative and never silently changes market."""
import json

import pytest


def api():
    from data_modules import writing_profile
    return writing_profile


@pytest.mark.parametrize("market,language,genre,unit", [
    ("domestic", "zh", "规则怪谈+悬疑", "characters"),
    ("overseas", "zh", "成长奇幻+LitRPG", "characters"),
    ("overseas", "en", "progression_fantasy+romantasy+litrpg", "words"),
])
def test_three_profiles_roundtrip(tmp_path, market, language, genre, unit):
    mod = api()
    profile = mod.build_writing_profile(market=market, body_language=language,
                                       genre=genre, allow_draft_rules=True)
    mod.save_writing_profile(tmp_path, profile)
    actual = mod.load_writing_profile(tmp_path)
    assert actual.market == market
    assert actual.body_language == language
    assert actual.chapter_unit == unit
    assert actual.secondary_genres
    assert actual.model_dump() == profile.model_dump()
    assert actual.reference() == profile.reference()
    bundles = mod.load_rule_bundles(actual)
    assert bundles["language_rules"]["body_language"] == language
    if market == "overseas":
        assert [r["id"] for r in bundles["genre_rules"]] == [actual.primary_genre, *actual.secondary_genres]
        assert all(r["market"] == "overseas" for r in bundles["genre_rules"])


def test_market_and_language_independent():
    mod = api()
    zh = mod.build_writing_profile(market="overseas", body_language="zh", genre="litrpg", allow_draft_rules=True)
    en = mod.build_writing_profile(market="overseas", body_language="en", genre="litrpg", allow_draft_rules=True)
    assert zh.rule_pack_versions == en.rule_pack_versions
    assert zh.chapter_unit == "characters"
    assert en.chapter_unit == "words"
    assert zh.reference()["sha256"] != en.reference()["sha256"]


def test_unknown_secondary_rejected_even_when_primary_matches():
    mod = api()
    with pytest.raises(ValueError, match="未知.*neverland"):
        mod.build_writing_profile(market="overseas", genre="litrpg+neverland", allow_draft_rules=True)
    with pytest.raises(ValueError, match="未知.*不存在"):
        mod.build_writing_profile(genre="仙侠+不存在的题材")


@pytest.mark.parametrize("kwargs", [
    {"genre": "玄幻", "secondary_genres": ["毫无注册的悬疑乱码"]},
    {"genre": "玄幻+毫无注册的悬疑乱码"},
])
def test_unknown_secondary_containing_known_label_is_not_fuzzy_matched(kwargs):
    with pytest.raises(ValueError, match="未知.*毫无注册"):
        api().build_writing_profile(**kwargs)


def test_legacy_without_any_new_markers_keeps_domestic_behavior(tmp_path):
    mod = api()
    profile = mod.load_writing_profile(tmp_path, state={"project_info": {"genre": "仙侠"}})
    assert profile.market == "domestic" and profile.body_language == "zh"
    assert profile.reference()["legacy"] is True
    assert not (tmp_path / ".story-system" / "WRITING_PROFILE.json").exists()


@pytest.mark.parametrize("marker", [
    {"market": "overseas"}, {"writing_profile": {"market": "overseas"}},
    {"writing_profile_ref": {"sha256": "old"}}, {"body_language": "en"},
])
def test_missing_explicit_profile_never_falls_back(tmp_path, marker):
    with pytest.raises(ValueError, match="WRITING_PROFILE"):
        api().load_writing_profile(tmp_path, state={"project_info": marker})


def test_missing_profile_detected_from_contract(tmp_path):
    story = tmp_path / ".story-system"
    story.mkdir()
    (story / "MASTER_SETTING.json").write_text(json.dumps({"meta": {"writing_profile_ref": {"sha256": "old"}}}), encoding="utf-8")
    with pytest.raises(ValueError, match="WRITING_PROFILE"):
        api().load_writing_profile(tmp_path)


@pytest.mark.parametrize("mutation", ["corrupt", "version", "unknown_field", "missing_secondary_version", "wrong_unit", "wrong_market"])
def test_invalid_profile_fails_closed(tmp_path, mutation):
    mod = api()
    profile = mod.build_writing_profile(market="overseas", body_language="en", genre="litrpg+romantasy", allow_draft_rules=True)
    mod.save_writing_profile(tmp_path, profile)
    path = tmp_path / ".story-system" / "WRITING_PROFILE.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    if mutation == "corrupt":
        path.write_text("{", encoding="utf-8")
    else:
        if mutation == "version": payload["rule_pack_versions"]["litrpg"] = "99.0.0"
        if mutation == "unknown_field": payload["typo_market"] = "domestic"
        if mutation == "missing_secondary_version": del payload["rule_pack_versions"]["romantasy"]
        if mutation == "wrong_unit": payload["chapter_unit"] = "characters"
        if mutation == "wrong_market": payload["market"] = "domestic"
        path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError): mod.load_writing_profile(tmp_path)


def test_save_refuses_changed_profile(tmp_path):
    mod = api()
    p = mod.build_writing_profile(genre="仙侠")
    mod.save_writing_profile(tmp_path, p)
    old = (tmp_path / ".story-system" / "WRITING_PROFILE.json").read_bytes()
    mod.save_writing_profile(tmp_path, p)
    with pytest.raises(ValueError, match="已有"):
        mod.save_writing_profile(tmp_path, mod.build_writing_profile(genre="悬疑"))
    assert old == (tmp_path / ".story-system" / "WRITING_PROFILE.json").read_bytes()


@pytest.mark.parametrize("kwargs", [
    {"market": "domestic", "body_language": "en", "genre": "仙侠"},
    {"market": "overseas", "genre": "litrpg", "chapter_unit": "words"},
    {"market": "overseas", "genre": "litrpg", "chapter_length": 0},
    {"market": "overseas", "genre": "litrpg"},
])
def test_invalid_combination_or_unapproved_draft(kwargs):
    with pytest.raises(ValueError): api().build_writing_profile(**kwargs)


def test_domestic_compound_and_western_fantasy_not_xianxia():
    from data_modules.genre_aliases import to_profile_key
    p = api().build_writing_profile(genre="西幻+悬疑+种田")
    assert p.primary_genre == "西幻"
    assert p.secondary_genres == ["悬疑", "种田"]
    assert to_profile_key("西幻") != "xianxia"


def test_domestic_genres_sharing_a_template_remain_distinct():
    profile = api().build_writing_profile(genre="玄幻", secondary_genres=["仙侠", "悬疑"])
    assert profile.primary_genre == "玄幻"
    assert profile.secondary_genres == ["仙侠", "悬疑"]


def test_language_versions_and_optional_choices_survive(tmp_path):
    mod = api()
    p = mod.build_writing_profile(market="overseas", body_language="en", genre="LitRPG",
                                 chapter_length=1800, pov="third_limited", tense="past",
                                 platform=None, allow_draft_rules=True)
    mod.save_writing_profile(tmp_path, p)
    result = mod.load_writing_profile(tmp_path)
    assert result.chapter_length == 1800
    assert result.pov == "third_limited" and result.tense == "past"
    assert result.platform is None
    assert result.reference()["language_pack_version"] == p.language_pack_version


@pytest.mark.parametrize("folder", ["chapters", "volumes", "reviews", "commits"])
def test_orphaned_explicit_child_contract_cannot_become_legacy(tmp_path, folder):
    child = tmp_path / f".story-system/{folder}/chapter_001.json"
    child.parent.mkdir(parents=True)
    child.write_text(json.dumps({"meta": {"writing_profile_ref": {"sha256": "old"}}}), encoding="utf-8")
    with pytest.raises(ValueError, match="WRITING_PROFILE"):
        api().load_writing_profile(tmp_path)


def test_corrupt_state_with_only_reference_marker_fails_closed(tmp_path):
    path = tmp_path / ".webnovel/state.json"
    path.parent.mkdir()
    path.write_text('{"writing_profile_ref": ', encoding="utf-8")
    with pytest.raises(ValueError, match="WRITING_PROFILE"):
        api().load_writing_profile(tmp_path)


@pytest.mark.parametrize("payload", [[], None, "wrong"])
def test_profile_wrong_json_shape_rejected(tmp_path, payload):
    path = tmp_path / ".story-system/WRITING_PROFILE.json"
    path.parent.mkdir()
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="WRITING_PROFILE"):
        api().load_writing_profile(tmp_path)


def test_legacy_contract_empty_schema_defaults_are_not_configuration_markers(tmp_path):
    story = tmp_path / ".story-system"
    story.mkdir()
    payload = {"meta": {"contract_type": "MASTER_SETTING", "writing_profile_ref": {},
                         "rule_pack_versions": {}, "market": None, "body_language": None}}
    (story / "MASTER_SETTING.json").write_text(json.dumps(payload), encoding="utf-8")
    assert api().load_writing_profile(tmp_path).reference()["legacy"] is True


def test_legacy_chapter_measurement_metadata_is_not_project_configuration(tmp_path):
    state = {"chapter_meta": {"1": {"body_language": "zh", "word_count": 20, "count_unit": "characters"}}}
    assert api().load_writing_profile(tmp_path, state=state).reference()["legacy"] is True


def test_explicitly_legacy_reference_can_be_displayed_without_profile(tmp_path):
    old = api().load_writing_profile(tmp_path)
    state = {"project_info": {"writing_profile_ref": old.reference()}}
    assert api().load_writing_profile(tmp_path, state=state).reference()["legacy"] is True
