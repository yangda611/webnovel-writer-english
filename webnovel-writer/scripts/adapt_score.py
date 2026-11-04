#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
合并多份 adapt-reviewer 审查 JSON：校验扣分明细，按维度取平均（3 份及以上取中位数）。

用法：
  python -X utf8 adapt_score.py a.json b.json [c.json] [--out merged.json]

退出码：0 = 合并后通过；1 = 未通过；2 = 输入无效或审查分歧过大（需要再加一份审查）。
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path
from typing import Any

DIMENSIONS: dict[str, int] = {
    "fidelity": 20,
    "hook_open": 15,
    "escalation": 15,
    "payoff": 15,
    "hook_end": 15,
    "visual": 10,
    "dialogue": 10,
}
PASS_TOTAL = 90
PASS_DIM_RATIO = 0.7
DIVERGENCE_LIMIT = 8
HEAVY_POINTS = 2


def _extract_json(text: str) -> dict[str, Any]:
    """审查输出可能带 ```json 包裹或前后说明，取第一个完整 JSON 对象。"""
    text = text.strip().lstrip("﻿")
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("未找到 JSON 对象")
    return json.loads(text[start : end + 1])


def validate_review(review: dict[str, Any]) -> list[str]:
    """返回问题列表；为空表示这份审查自洽。"""
    problems: list[str] = []
    scores = review.get("scores") or {}
    deductions = review.get("deductions")
    by_dim: dict[str, int] = {dim: 0 for dim in DIMENSIONS}
    if isinstance(deductions, list):
        for item in deductions:
            dim = str((item or {}).get("dim") or "")
            if dim not in by_dim:
                problems.append(f"扣分项维度非法：{dim!r}")
                continue
            try:
                by_dim[dim] += int(item.get("points") or 0)
            except (TypeError, ValueError):
                problems.append(f"扣分项分值非法：{item!r}")
    else:
        problems.append("缺少 deductions 扣分明细")

    total = 0
    for dim, max_score in DIMENSIONS.items():
        entry = scores.get(dim)
        if not isinstance(entry, dict) or "score" not in entry:
            problems.append(f"缺少维度 {dim}")
            continue
        try:
            score = int(entry["score"])
        except (TypeError, ValueError):
            problems.append(f"{dim} 分数不是整数")
            continue
        if not 0 <= score <= max_score:
            problems.append(f"{dim} 分数 {score} 超出 0-{max_score}")
        total += score
        if isinstance(deductions, list) and max_score - score != by_dim[dim]:
            problems.append(f"{dim} 扣了 {max_score - score} 分，但扣分明细合计 {by_dim[dim]}")
    claimed = review.get("total")
    if claimed is not None and claimed != total:
        problems.append(f"total 写的是 {claimed}，各项相加是 {total}")
    return problems


def _dim_scores(review: dict[str, Any]) -> dict[str, int]:
    return {dim: int(review["scores"][dim]["score"]) for dim in DIMENSIONS}


def merge_reviews(reviews: list[dict[str, Any]]) -> dict[str, Any]:
    if len(reviews) < 2:
        raise ValueError("至少需要 2 份审查")
    per_dim = [_dim_scores(r) for r in reviews]
    totals = [sum(d.values()) for d in per_dim]
    combine = statistics.median if len(reviews) >= 3 else statistics.mean
    merged_dims = {dim: round(combine([d[dim] for d in per_dim]), 1) for dim in DIMENSIONS}
    merged_total = round(sum(merged_dims.values()), 1)

    blocking: list[str] = []
    for review in reviews:
        for issue in review.get("blocking_issues") or []:
            if issue not in blocking:
                blocking.append(issue)

    rule_hits: dict[tuple[str, str], int] = {}
    for review in reviews:
        seen: set[tuple[str, str]] = set()
        for item in review.get("deductions") or []:
            key = (str(item.get("dim")), str(item.get("rule")))
            if key not in seen:
                seen.add(key)
                rule_hits[key] = rule_hits.get(key, 0) + 1
    agreed = [{"dim": dim, "rule": rule} for (dim, rule), hits in rule_hits.items() if hits >= 2]

    # 校准 3.2：90 分要求没有扣 2 分以上的项。多数审查都给出的重扣项会阻止通过。
    heavy_hits: dict[tuple[str, str], int] = {}
    for review in reviews:
        seen_heavy: set[tuple[str, str]] = set()
        for item in review.get("deductions") or []:
            try:
                points = int(item.get("points") or 0)
            except (TypeError, ValueError):
                continue
            key = (str(item.get("dim")), str(item.get("rule")))
            if points >= HEAVY_POINTS and key not in seen_heavy:
                seen_heavy.add(key)
                heavy_hits[key] = heavy_hits.get(key, 0) + 1
    quorum = len(reviews) // 2 + 1
    heavy = [{"dim": dim, "rule": rule} for (dim, rule), hits in heavy_hits.items() if hits >= quorum]

    divergence = max(totals) - min(totals)
    dim_floor_ok = all(merged_dims[dim] >= DIMENSIONS[dim] * PASS_DIM_RATIO for dim in DIMENSIONS)
    return {
        "reviewers": len(reviews),
        "totals": totals,
        "divergence": divergence,
        "needs_extra_review": len(reviews) == 2 and divergence > DIVERGENCE_LIMIT,
        "scores": merged_dims,
        "total": merged_total,
        "agreed_deductions": agreed,
        "heavy_deductions": heavy,
        "blocking_issues": blocking,
        "pass": merged_total >= PASS_TOTAL and dim_floor_ok and not blocking and not heavy,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="合并多份 adapt-reviewer 审查结果")
    parser.add_argument("reviews", nargs="+")
    parser.add_argument("--out", default=None)
    args = parser.parse_args(argv)

    reviews: list[dict[str, Any]] = []
    invalid = False
    for path in args.reviews:
        try:
            review = _extract_json(Path(path).read_text(encoding="utf-8-sig"))
        except (OSError, ValueError) as exc:
            print(f"[INVALID] {path}: {exc}")
            invalid = True
            continue
        problems = validate_review(review)
        if problems:
            invalid = True
            print(f"[INVALID] {path}")
            for problem in problems:
                print(f"  - {problem}")
        reviews.append(review)
    if invalid:
        print("审查 JSON 不自洽，需要让 adapt-reviewer 重新输出。")
        return 2

    merged = merge_reviews(reviews)
    payload = json.dumps(merged, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(payload + "\n", encoding="utf-8")
    print(payload)
    if merged["needs_extra_review"]:
        print(f"两份审查总分相差 {merged['divergence']} 分（>{DIVERGENCE_LIMIT}），请再调用一次 adapt-reviewer 后三份一起合并。")
        return 2
    return 0 if merged["pass"] else 1


if __name__ == "__main__":
    try:
        from runtime_compat import enable_windows_utf8_stdio

        enable_windows_utf8_stdio(skip_in_pytest=True)
    except Exception:  # pragma: no cover
        pass
    sys.exit(main())
