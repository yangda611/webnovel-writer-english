"""CLI callers get the same market boundary as runtime reference queries."""
import csv
import json

import pytest

from data_modules.writing_profile import build_writing_profile, save_writing_profile
from reference_search import main


@pytest.fixture
def reference_project(tmp_path):
    root = tmp_path / "book"
    profile = build_writing_profile(market="overseas", body_language="zh", genre="litrpg+romantasy", allow_draft_rules=True)
    save_writing_profile(root, profile)
    csv_dir = tmp_path / "csv"
    csv_dir.mkdir()
    with (csv_dir / "场景写法.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["编号", "适用技能", "适用题材", "关键词", "核心摘要", "market", "human_reviewed"])
        writer.writeheader()
        for key, market, reviewed, genre in [
            ("old", "", "", "全部"), ("foreign_primary", "overseas", "", "litrpg"),
            ("foreign_secondary", "overseas", "", "romantasy"), ("shared", "shared", "true", "全部"),
            ("unreviewed", "shared", "false", "全部"),
        ]:
            writer.writerow({"编号": key, "适用技能": "write", "适用题材": genre, "关键词": "bridge",
                             "核心摘要": "bridge scene", "market": market, "human_reviewed": reviewed})
    return root, csv_dir


def test_reference_cli_reads_market_and_all_genres_from_project(reference_project, capsys):
    root, csv_dir = reference_project
    main(["--project-root", str(root), "--csv-dir", str(csv_dir), "--skill", "write", "--query", "bridge", "--max-results", "20"])
    result = json.loads(capsys.readouterr().out)
    assert {item["编号"] for item in result["data"]["results"]} == {"foreign_primary", "foreign_secondary", "shared"}


def test_reference_cli_explicit_market_and_project_conflict_fails(reference_project, capsys):
    root, csv_dir = reference_project
    with pytest.raises(SystemExit) as error:
        main(["--project-root", str(root), "--market", "domestic", "--csv-dir", str(csv_dir), "--skill", "write", "--query", "bridge"])
    assert error.value.code == 2
    assert "conflicts" in capsys.readouterr().err


def test_reference_cli_damaged_profile_never_searches_domestic(reference_project, capsys):
    root, csv_dir = reference_project
    (root / ".story-system/WRITING_PROFILE.json").write_text("{", encoding="utf-8")
    with pytest.raises(SystemExit) as error:
        main(["--project-root", str(root), "--csv-dir", str(csv_dir), "--skill", "write", "--query", "bridge"])
    assert error.value.code == 2
    assert not capsys.readouterr().out
