"""Pinned projects must survive a newer installed editorial draft."""
import json

import pytest

from data_modules import rule_registry
from data_modules.writing_profile import WritingProfile, load_writing_profile, save_writing_profile


@pytest.fixture
def registry(tmp_path, monkeypatch):
    root = tmp_path / "rules"
    for kind, key in (("genres", "litrpg"), ("languages", "en")):
        source = rule_registry.read_pack(kind, key)
        for version, path in (
            ("1.1.0", root / kind / f"{key}.json"),
            ("1.1.0", root / "versions" / kind / key / "1.1.0.json"),
            ("1.0.0", root / "versions" / kind / key / "1.0.0.json"),
        ):
            path.parent.mkdir(parents=True, exist_ok=True)
            pack = {**source, "version": version, "reader_promise": f"promise-{version}"}
            path.write_text(json.dumps(pack), encoding="utf-8")
    monkeypatch.setattr(rule_registry, "RULES_ROOT", root)
    return root


def test_pinned_pack_uses_archive_instead_of_newer_default(registry):
    assert rule_registry.read_pack("genres", "litrpg")["reader_promise"] == "promise-1.1.0"
    assert rule_registry.read_pack("genres", "litrpg", "1.0.0")["reader_promise"] == "promise-1.0.0"


def test_pinned_archive_does_not_depend_on_latest_being_readable(registry):
    (registry / "genres/litrpg.json").write_text("broken", encoding="utf-8")
    assert rule_registry.read_pack("genres", "litrpg", "1.0.0")["version"] == "1.0.0"


def test_pinned_current_release_reads_immutable_archive(registry):
    archive = registry / "versions/genres/litrpg/1.1.0.json"
    latest = registry / "genres/litrpg.json"
    original_promise = json.loads(archive.read_text(encoding="utf-8"))["reader_promise"]
    current = json.loads(latest.read_text(encoding="utf-8"))
    current["reader_promise"] = "mutated without a version bump"
    latest.write_text(json.dumps(current), encoding="utf-8")

    assert rule_registry.read_pack("genres", "litrpg", "1.1.0")["reader_promise"] == original_promise


def test_missing_pinned_archive_is_an_error_even_if_current_matches(registry):
    (registry / "versions/genres/litrpg/1.1.0.json").unlink()

    with pytest.raises(rule_registry.RulePackError, match="归档"):
        rule_registry.read_pack("genres", "litrpg", "1.1.0")


@pytest.mark.parametrize("damage", ["corrupt", "wrong_version", "wrong_market"])
def test_damaged_pin_never_silently_uses_latest(registry, damage):
    path = registry / "versions/genres/litrpg/1.0.0.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    if damage == "corrupt":
        path.write_text("{", encoding="utf-8")
    else:
        data["version" if damage == "wrong_version" else "market"] = "1.1.0" if damage == "wrong_version" else "domestic"
        path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(rule_registry.RulePackError):
        rule_registry.read_pack("genres", "litrpg", "1.0.0")


@pytest.mark.parametrize("version", ["../1.0.0", "1/2/3", "", "01", 1])
def test_pin_is_a_safe_version_identifier(registry, version):
    with pytest.raises(rule_registry.RulePackError, match="版本"):
        rule_registry.read_pack("genres", "litrpg", version)


@pytest.mark.parametrize("field,value", [
    ("scope", "bad"), ("editorial_framework", ["bad"]),
    ("editorial_framework", {"primary_application": "only part of the framework"}),
])
def test_malformed_editorial_data_is_a_rule_pack_error(registry, field, value):
    path = registry / "genres/litrpg.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data[field] = value
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(rule_registry.RulePackError, match="字段"):
        rule_registry.read_pack("genres", "litrpg")


def test_old_package_without_editorial_framework_still_loads(registry):
    path = registry / "versions/genres/litrpg/1.0.0.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data.pop("editorial_framework", None)
    path.write_text(json.dumps(data), encoding="utf-8")
    assert rule_registry.read_pack("genres", "litrpg", "1.0.0")["reader_promise"] == "promise-1.0.0"


def test_old_profile_load_and_reinit_preserve_pins_and_content(tmp_path, registry, monkeypatch):
    import init_project as init_module

    project = tmp_path / "book"
    profile = WritingProfile(market="overseas", body_language="en", primary_genre="litrpg",
                             chapter_length=1500, chapter_unit="words", rule_pack_versions={"litrpg": "1.0.0"},
                             language_pack_version="1.0.0", allow_draft_rules=True)
    # Simulate an existing 1.0.0 project after the distribution was upgraded.
    story = project / ".story-system"
    story.mkdir(parents=True)
    (story / "WRITING_PROFILE.json").write_text(profile.model_dump_json(), encoding="utf-8")
    state = project / ".webnovel/state.json"
    state.parent.mkdir()
    state.write_text(json.dumps({"project_info": {"title": "Old book"}}), encoding="utf-8")
    manuscript = project / "正文/第0001章.md"
    manuscript.parent.mkdir()
    manuscript.write_text("An existing scene.", encoding="utf-8")
    before = {path: path.read_bytes() for path in (story / "WRITING_PROFILE.json", state, manuscript)}
    assert load_writing_profile(project).reference() == profile.reference()
    monkeypatch.setattr(init_module, "is_git_available", lambda: False)
    monkeypatch.setattr(init_module, "write_current_project_pointer", lambda root: None)
    init_module.init_project(str(project), "Old book", "litrpg")
    assert all(path.read_bytes() == content for path, content in before.items())
    save_writing_profile(project, load_writing_profile(project))
    assert (story / "WRITING_PROFILE.json").read_bytes() == before[story / "WRITING_PROFILE.json"]
