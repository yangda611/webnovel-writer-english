#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for adapt_score.py — merging adapt-reviewer JSON outputs."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import adapt_score  # noqa: E402


def _review(deduct: dict[str, int], *, blocking: list[str] | None = None, wrap: bool = False) -> dict:
    scores = {}
    deductions = []
    for dim, max_score in adapt_score.DIMENSIONS.items():
        points = deduct.get(dim, 0)
        scores[dim] = {"score": max_score - points, "max": max_score, "evidence": "", "fix": ""}
        if points:
            deductions.append({"dim": dim, "rule": f"{dim}-rule", "points": points, "where": "L1", "quote": ""})
    return {
        "scores": scores,
        "deductions": deductions,
        "total": sum(s["score"] for s in scores.values()),
        "blocking_issues": blocking or [],
    }


def _write(tmp_path: Path, name: str, review: dict, *, wrap: bool = False) -> str:
    text = json.dumps(review, ensure_ascii=False)
    if wrap:
        text = "审查结果如下：\n```json\n" + text + "\n```"
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return str(path)


def test_validate_detects_mismatch():
    review = _review({"payoff": 3})
    review["deductions"][0]["points"] = 2
    review["total"] = 1
    problems = adapt_score.validate_review(review)
    assert any("payoff" in p and "合计 2" in p for p in problems)
    assert any("total" in p for p in problems)


def test_merge_two_mean_and_agreed_deductions():
    a = _review({"hook_open": 2, "visual": 1})
    b = _review({"hook_open": 4})
    merged = adapt_score.merge_reviews([a, b])
    assert merged["scores"]["hook_open"] == 12.0
    assert merged["scores"]["visual"] == 9.5
    assert merged["total"] == 96.5
    assert merged["agreed_deductions"] == [{"dim": "hook_open", "rule": "hook_open-rule"}]
    # 两份审查都对 hook_open 扣了 2 分以上，按校准 3.2 不能通过。
    assert merged["heavy_deductions"] == [{"dim": "hook_open", "rule": "hook_open-rule"}]
    assert merged["pass"] is False


def test_merge_three_median_and_blocking():
    reviews = [_review({"payoff": 1}), _review({"payoff": 9}), _review({"payoff": 2}, blocking=["改了结果"])]
    merged = adapt_score.merge_reviews(reviews)
    assert merged["scores"]["payoff"] == 13
    assert merged["blocking_issues"] == ["改了结果"]
    assert merged["pass"] is False


def test_dimension_floor_blocks_pass():
    merged = adapt_score.merge_reviews([_review({"payoff": 5}), _review({"payoff": 5})])
    assert merged["total"] == 95
    assert merged["pass"] is False


def test_cli_divergence_requests_third_review(tmp_path, capsys):
    a = _write(tmp_path, "a.json", _review({}))
    b = _write(tmp_path, "b.json", _review({"payoff": 4, "hook_open": 6}), wrap=True)
    code = adapt_score.main([a, b, "--out", str(tmp_path / "m.json")])
    out = capsys.readouterr().out
    assert code == 2
    assert "相差 10" in out
    assert json.loads((tmp_path / "m.json").read_text(encoding="utf-8"))["needs_extra_review"] is True


def test_cli_invalid_review(tmp_path, capsys):
    bad = _review({"payoff": 3})
    bad.pop("deductions")
    a = _write(tmp_path, "a.json", bad)
    b = _write(tmp_path, "b.json", _review({}))
    code = adapt_score.main([a, b])
    assert code == 2
    assert "INVALID" in capsys.readouterr().out


def test_cli_fail_exit_code(tmp_path):
    a = _write(tmp_path, "a.json", _review({"payoff": 4, "fidelity": 7}))
    b = _write(tmp_path, "b.json", _review({"payoff": 4, "fidelity": 7}))
    assert adapt_score.main([a, b]) == 1


def test_heavy_deduction_agreed_by_majority_blocks_pass():
    a = _review({"fidelity": 2})
    b = _review({"fidelity": 2})
    merged = adapt_score.merge_reviews([a, b])
    assert merged["total"] == 98
    assert merged["heavy_deductions"] == [{"dim": "fidelity", "rule": "fidelity-rule"}]
    assert merged["pass"] is False


def test_heavy_deduction_from_single_reviewer_does_not_block():
    merged = adapt_score.merge_reviews([_review({"fidelity": 2}), _review({})])
    assert merged["heavy_deductions"] == []
    assert merged["pass"] is True
