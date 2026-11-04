#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for adapt_lint.py — short-drama script / manju storyboard format checks."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import adapt_lint  # noqa: E402


def _short_drama(dialogue_count: int = 20, *, extra: str = "", opening: str | None = None) -> str:
    opening = opening or "△（特写）一封未拆的信，火漆上一个“纳”字。"
    lines = [
        "# 第1集：废物的测试石",
        "",
        "> 来源：第0004章-迦南学院的考验",
        "> 时长目标：120秒",
        "",
        "## 场1 内 客房 晨",
        "**人物**：萧炎、药老",
        opening,
    ]
    for i in range(dialogue_count):
        if i == dialogue_count // 2:
            lines += ["", "## 场2 外 演武场 日", "**人物**：萧炎、韩越"]
        lines.append(f"**{'萧炎' if i % 2 else '韩越'}**（冷声）：这是第{i}句台词，你听清楚了没有，我只说一遍。")
        lines.append(f"△（{'近景' if i % 3 else '全景'}）对方攥紧拳头，眼神一沉。")
    lines += [extra, "", "【本集完】", "", "> 🎣 结尾钩子：身份危机 · 长老盯住戒指，低声说这股气息不可能"]
    return "\n".join(lines)


def _write(tmp_path: Path, name: str, text: str) -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def test_short_drama_valid_passes(tmp_path):
    result = adapt_lint.lint_file(_write(tmp_path, "ep.md", _short_drama()), "short-drama")
    assert result.ok, result.errors
    assert result.metrics["scenes"] == 2
    assert result.metrics["dialogue_lines"] == 20
    assert 90 <= result.metrics["est_duration_sec"] <= 150


def test_short_drama_naked_narration_is_error(tmp_path):
    text = _short_drama(extra="萧炎缓缓站起身来，活动了一下筋骨。")
    result = adapt_lint.lint_file(_write(tmp_path, "ep.md", text), "short-drama")
    assert any("裸叙述" in e for e in result.errors)


def test_short_drama_unfilmable_action_is_error(tmp_path):
    text = _short_drama(extra="△（近景）萧炎心中暗道，绝不能失败。")
    result = adapt_lint.lint_file(_write(tmp_path, "ep.md", text), "short-drama")
    assert any("拍不出来" in e for e in result.errors)


def test_short_drama_too_few_dialogue_and_missing_hook(tmp_path):
    text = _short_drama(dialogue_count=6).replace("> 🎣 结尾钩子：身份危机 · 长老盯住戒指，低声说这股气息不可能", "")
    result = adapt_lint.lint_file(_write(tmp_path, "ep.md", text), "short-drama")
    joined = "\n".join(result.errors)
    assert "有效对白" in joined
    assert "结尾钩子" in joined


def test_short_drama_weak_opening_is_error(tmp_path):
    text = _short_drama(opening="△（全景）晨光照进房间。\n△（中景）窗外鸟鸣。\n△（中景）桌上一杯茶。\n△（全景）房门紧闭。")
    result = adapt_lint.lint_file(_write(tmp_path, "ep.md", text), "short-drama")
    assert any("黄金3秒" in e for e in result.errors)


def test_short_drama_scene_header_requires_time_and_interior(tmp_path):
    text = _short_drama().replace("## 场1 内 客房 晨", "## 场1 客房")
    result = adapt_lint.lint_file(_write(tmp_path, "ep.md", text), "short-drama")
    assert any("场头" in e for e in result.errors)


def _manju(shots: int = 24, *, register_speaker: bool = True, desc: str = "萧炎站在黑色测试石前，右手按上石面，石心浮起淡金光芒") -> str:
    assets = ["- **萧炎**：16岁少年，黑色短碎发，黑色劲装，左手食指戴古朴黑戒"]
    if register_speaker:
        assets.append("- **韩越**：中年考官，鹰钩鼻，灰色短须，墨绿长袍佩学院徽章")
    rows = []
    sizes = ["大特写", "特写", "近景", "中景", "全景"]
    moves = ["急推", "固定", "慢推", "摇", "跟"]
    for i in range(1, shots + 1):
        line = "韩越：萧炎，少一关就滚" if i % 4 == 0 else "—"
        rows.append(f"| {i} | 3.5s | {sizes[i % 5]} | {moves[i % 5]} | {desc} | {line} | 低频嗡鸣 |")
    return "\n".join(
        [
            "# 第1集：废物的测试石",
            "> 来源：第0004章",
            "> 时长目标：90秒",
            "",
            "## 角色与场景资产",
            *assets,
            "",
            "## 分镜",
            "| 镜号 | 时长 | 景别 | 运镜 | 画面 | 台词/字幕 | 音效/音乐 |",
            "|------|------|------|------|------|-----------|-----------|",
            *rows,
            "",
            "【本集完】",
            "> 🎣 结尾钩子：身份危机 · 长老瞳孔骤缩，盯住萧炎的戒指",
        ]
    )


def test_manju_valid_passes(tmp_path):
    result = adapt_lint.lint_file(_write(tmp_path, "ep.md", _manju()), "manju")
    assert result.ok, result.errors
    assert result.metrics["shots"] == 24
    assert result.metrics["total_sec"] == 84.0


def test_manju_unregistered_speaker_is_error(tmp_path):
    result = adapt_lint.lint_file(_write(tmp_path, "ep.md", _manju(register_speaker=False)), "manju")
    assert any("未登记资产" in e and "韩越" in e for e in result.errors)


def test_manju_short_description_and_dense_bubble(tmp_path):
    text = _manju(desc="测试开始")
    text = text.replace("韩越：萧炎，少一关就滚", "韩越：萧炎你给我听好了今天这一关你要是过不去就立刻给我滚出迦南学院永远别回来")
    result = adapt_lint.lint_file(_write(tmp_path, "ep.md", text), "manju")
    joined = "\n".join(result.errors)
    assert "画面描述不足" in joined
    assert "字/秒" in joined or "气泡" in joined


def test_manju_missing_table_is_error(tmp_path):
    result = adapt_lint.lint_file(_write(tmp_path, "ep.md", "# 第1集：标题\n> 来源：第1章\n"), "manju")
    assert any("分镜表" in e for e in result.errors)


def test_profile_overrides_and_cli_json(tmp_path, capsys):
    project = tmp_path / "book"
    (project / "改编").mkdir(parents=True)
    (project / "改编" / "ADAPT_PROFILE.json").write_text(
        json.dumps({"lint": {"short-drama": {"dialogue_range": [2, 40], "duration_range": [10, 200], "unknown": 1}}}),
        encoding="utf-8",
    )
    ep = _write(tmp_path, "ep.md", _short_drama(dialogue_count=6))
    code = adapt_lint.main(["--mode", "short-drama", "--project-root", str(project), "--format", "json", str(ep)])
    payload = json.loads(capsys.readouterr().out)
    assert payload[0]["ok"] is True, payload[0]["errors"]
    assert code == 0


def test_cli_text_failure_exit_code(tmp_path, capsys):
    ep = _write(tmp_path, "ep.md", "随便写的一段话")
    code = adapt_lint.main(["--mode", "short-drama", str(ep)])
    out = capsys.readouterr().out
    assert code == 1
    assert "[FAIL]" in out


def test_short_drama_wake_up_opening_and_relief_before_hook(tmp_path):
    text = _short_drama(opening="△（大特写）萧炎猛地睁眼，晨光照在脸上。")
    text = text.replace("\n\n【本集完】", "\n**萧炎**（OS）：第一步，成了。\n\n【本集完】")
    result = adapt_lint.lint_file(_write(tmp_path, "ep.md", text), "short-drama")
    joined = "\n".join(result.errors)
    assert "起床" in joined
    assert "收束性" in joined


def _replace_desc(text: str, shot: int, desc: str) -> str:
    import re as _re

    return _re.sub(
        rf"^(\| {shot} \|[^|]*\|[^|]*\|[^|]*\| )[^|]*( \|)",
        lambda m: m.group(1) + desc + m.group(2),
        text,
        count=1,
        flags=_re.M,
    )


def test_manju_frame_rules(tmp_path):
    text = _manju()
    text = _replace_desc(text, 2, "萧炎攥紧拳头，随即又松开，抬头看向远处的看台")
    text = _replace_desc(text, 3, "镜头从高空降下，俯瞰演武场上的上百名考生")
    text = _replace_desc(text, 5, "测试石表面浮现四个金色大字\"斗者九星\"")
    result = adapt_lint.lint_file(_write(tmp_path, "ep.md", text), "manju")
    joined = "\n".join(result.errors)
    assert "镜2" in joined and "定格" in joined
    assert "镜3" in joined and "运镜列" in joined
    assert "镜5" in joined and "字幕" in joined


def test_manju_invisible_and_generic_reference(tmp_path):
    text = _manju()
    text = _replace_desc(text, 2, "萧炎的手掌按在冰冷的测试石表面，手背青筋凸起")
    text = _replace_desc(text, 3, "对手的右拳裹着淡黄斗气，正面直轰向镜头")
    result = adapt_lint.lint_file(_write(tmp_path, "ep.md", text), "manju")
    assert any("镜2" in e and "看不见" in e for e in result.errors)
    assert any("镜3" in w and "泛称" in w for w in result.warnings)


def test_manju_two_body_parts_in_closeup(tmp_path):
    text = _replace_desc(_manju(), 1, "萧炎半张的五指间光芒溢出，照亮他收缩的瞳孔")
    result = adapt_lint.lint_file(_write(tmp_path, "ep.md", text), "manju")
    assert any("镜1" in e and "取景框" in e for e in result.errors)
