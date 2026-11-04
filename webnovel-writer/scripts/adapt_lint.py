#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
短剧剧本 / 漫剧分镜脚本的确定性格式与体量质检。

只检查可机械验证的指标（结构、对白量、镜头数、时长估算、字幕可读性、
裸叙述泄漏等）。叙事质量由 adapt-reviewer agent 另行评分，本脚本不打分。

用法：
  python -X utf8 adapt_lint.py --mode short-drama 改编/短剧/第001集-xxx.md [...]
  python -X utf8 adapt_lint.py --mode manju 改编/漫剧/第001集-xxx.md --format json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

SHOT_SIZES = ("大远景", "远景", "全景", "中景", "中近景", "近景", "大特写", "特写")
CAMERA_MOVES = (
    "固定", "推", "拉", "摇", "移", "跟", "升", "降", "环绕", "甩", "变焦",
    "手持", "俯拍", "仰拍", "主观", "急推", "急拉", "慢推", "慢拉",
)

# 口播语速：中文短剧对白约 4.5 字/秒；动作/反应镜头按每行约 2.5 秒估算。
SPEECH_CHARS_PER_SEC = 4.5
ACTION_LINE_SEC = 2.5

DEFAULTS: dict[str, dict[str, Any]] = {
    "short-drama": {
        "duration_range": (90, 150),
        "scene_range": (2, 5),
        "dialogue_range": (18, 32),
        "os_ratio_max": 0.3,
        "dialogue_len_warn": 30,
        "dialogue_len_error": 45,
        "action_len_warn": 60,
        "min_shot_sizes": 3,
        "opening_window": 4,
    },
    "manju": {
        "duration_range": (60, 120),
        "shot_range": (18, 40),
        "shot_sec_range": (1.0, 6.0),
        "min_desc_chars": 12,
        "min_shot_sizes": 4,
        "min_camera_moves": 3,
        "bubble_chars_per_sec": 5.0,
        "line_len_error": 30,
        "opening_window": 3,
    },
}

EPISODE_TITLE_RE = re.compile(r"^#\s*第\s*(\d+)\s*集[:：]\s*(\S.*)$")
SCENE_RE = re.compile(r"^##\s*场\s*(\d+)\s*(.*)$")
DIALOGUE_RE = re.compile(r"^\*\*([^*]+?)\*\*\s*(?:[（(]([^）)]*)[）)])?\s*[:：]\s*(.+)$")
ACTION_RE = re.compile(r"^△\s*(?:[（(]([^）)]*)[）)])?\s*(.*)$")
END_MARK = "【本集完】"
HOOK_RE = re.compile(r"🎣\s*结尾钩子\s*[:：]\s*(\S.+)")
META_RE = re.compile(r"^>\s*")
OS_TAGS = ("OS", "os", "内心", "心声", "旁白", "画外音", "VO", "V.O.")
NEUTRAL_LINE_PREFIXES = ("【", "♪", "---", "**人物**", "**出场", ">", "<!--")


@dataclass
class LintResult:
    path: str
    mode: str
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.errors

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "mode": self.mode,
            "ok": self.ok,
            "errors": self.errors,
            "warnings": self.warnings,
            "metrics": self.metrics,
        }


def _spoken_text(text: str) -> str:
    """去掉括号舞台提示与标点，只留可读出的字。"""
    text = re.sub(r"[（(][^）)]*[）)]", "", text)
    return re.sub(r"[\s\"“”‘’'「」『』，。！？、；：…—\-~～,.!?;:]", "", text)


def _is_os(tag: str | None) -> bool:
    return bool(tag) and any(marker in tag for marker in OS_TAGS)


def _check_header(lines: list[str], result: LintResult) -> None:
    title_line = next((line for line in lines if line.strip()), "")
    match = EPISODE_TITLE_RE.match(title_line.strip())
    if not match:
        result.errors.append("首行必须是集标题：`# 第N集：标题`")
    else:
        result.metrics["episode"] = int(match.group(1))
        result.metrics["title"] = match.group(2).strip()
    meta = " ".join(line for line in lines[:15] if META_RE.match(line))
    if "来源" not in meta:
        result.errors.append("缺少 `> 来源：第NNNN章…` 元信息，无法回溯原著")
    if "时长" not in meta:
        result.warnings.append("缺少 `> 时长目标` 元信息")


def _check_ending(text: str, result: LintResult) -> None:
    if END_MARK not in text:
        result.errors.append(f"缺少结束标记 {END_MARK}")
    hook = HOOK_RE.search(text)
    if not hook:
        result.errors.append("缺少 `> 🎣 结尾钩子：类型 · 内容`")
    elif len(hook.group(1).strip()) < 8:
        result.errors.append("结尾钩子描述过短（<8 字），无法判断钩子是否成立")
UNFILMABLE_RE = re.compile(r"心中暗道|心想|心里想|暗自|内心深处|他感到|她感到|感到一丝|意识到|明白了|总而言之|不知道的是|鸦雀无声|目光如鹰|目光如炬")
# 漫剧画面里看不见的描述（藏在衣物里、温度、主观状态）。
INVISIBLE_RE = re.compile(r"袖中的?手|怀里的|冰冷的|滚烫的|不受控地|悄悄")
# 特写/大特写只能装下一个身体部位（用"前景/后景"明确构图的除外）。
BODY_REGIONS = {
    "面部": ("瞳孔", "眼睛", "双眼", "眼角", "嘴唇", "额头"),
    "手部": ("手指", "五指", "手掌", "掌心", "手腕", "拳头", "指缝", "指节"),
    "腿脚": ("脚跟", "脚尖", "脚步", "膝盖", "鞋"),
}
# 漫剧画面里用泛称代替资产名。
GENERIC_REF_RE = re.compile(r"^(?:对手|那人|对方|此人)")
# 起床 / 天气 / 空镜类开场：即使用了特写也不算冲击。
WEAK_OPENING_RE = re.compile(r"睁开?眼|醒来|醒了|起床|晨光|阳光照|鸟鸣|伸懒腰|空镜")
# 一镜多状态：漫剧一格只能是一个瞬间。
MULTI_STATE_RE = re.compile(r"随即|然后|接着|继而|又一点点|之后|转身离开|，又")
# 画面列里写运镜或要求画出文字。
CAMERA_IN_DESC_RE = re.compile(r"镜头(?:从|推|拉|摇|跟|降|升|缓缓|慢慢)")
TEXT_IN_IMAGE_RE = re.compile(r"(?:浮现|写着|印着|刻着)[^，。]{0,6}[\"“「][^\"”」]{2,}[\"”」]|大字")
# 钩子前的收束性 OS / 台词。
RELIEF_RE = re.compile(r"成了|搞定|终于|总算|松了口气|第一步")


def lint_short_drama(text: str, result: LintResult, cfg: dict[str, Any]) -> None:
    lines = text.splitlines()
    _check_header(lines, result)
    _check_ending(text, result)

    scenes = 0
    dialogue = 0
    os_lines = 0
    spoken_chars = 0
    action_lines = 0
    shot_sizes: set[str] = set()
    naked: list[int] = []
    first_content: list[str] = []
    in_scene = False
    scene_has_people = True
    last_lines: list[tuple[str, int, str]] = []

    for no, raw in enumerate(lines, 1):
        line = raw.strip()
        if not line or EPISODE_TITLE_RE.match(line):
            continue
        scene = SCENE_RE.match(line)
        if scene:
            if in_scene and not scene_has_people:
                result.warnings.append(f"场{scenes} 缺少 `**人物**：` 行")
            scenes += 1
            in_scene = True
            scene_has_people = False
            header = scene.group(2)
            if not re.search(r"[日夜晨昏]", header) or not re.search(r"[内外]", header):
                result.errors.append(f"第{no}行 场头需含 日/夜 与 内/外：`{line}`")
            continue
        if line.startswith("**人物**"):
            scene_has_people = True
            continue
        if META_RE.match(line) or line.startswith(NEUTRAL_LINE_PREFIXES):
            continue
        if not in_scene:
            naked.append(no)
            continue
        dlg = DIALOGUE_RE.match(line)
        if dlg:
            dialogue += 1
            spoken = _spoken_text(dlg.group(3))
            spoken_chars += len(spoken)
            if _is_os(dlg.group(2)):
                os_lines += 1
            if len(spoken) > cfg["dialogue_len_error"]:
                result.errors.append(f"第{no}行 单句台词 {len(spoken)} 字，超过 {cfg['dialogue_len_error']}，必须拆句或删减")
            elif len(spoken) > cfg["dialogue_len_warn"]:
                result.warnings.append(f"第{no}行 单句台词 {len(spoken)} 字，竖屏口播偏长")
            if len(first_content) < cfg["opening_window"]:
                first_content.append("dialogue")
            last_lines.append(("dialogue", no, dlg.group(3)))
            continue
        act = ACTION_RE.match(line)
        if act:
            action_lines += 1
            tag = act.group(1) or ""
            for size in SHOT_SIZES:
                if size in tag:
                    shot_sizes.add(size)
                    break
            body = act.group(2)
            if UNFILMABLE_RE.search(body):
                result.errors.append(f"第{no}行 动作行写了拍不出来的心理/总结：`{body[:24]}…`，改成可见动作或 OS")
            if len(_spoken_text(body)) > cfg["action_len_warn"]:
                result.warnings.append(f"第{no}行 动作行过长，拆成多个镜头")
            if not first_content and WEAK_OPENING_RE.search(body):
                result.errors.append(f"第{no}行 首镜是起床/天气/空镜类开场，黄金3秒要直接给冲突或异常")
            if len(first_content) < cfg["opening_window"]:
                first_content.append("impact" if any(k in tag for k in ("特写", "急推", "大特写")) else "action")
            last_lines.append(("action", no, body))
            continue
        naked.append(no)

    if in_scene and not scene_has_people:
        result.warnings.append(f"场{scenes} 缺少 `**人物**：` 行")

    for kind, no, body in last_lines[-4:]:
        if kind == "dialogue" and RELIEF_RE.search(body):
            result.errors.append(f"第{no}行 结尾钩子前出现收束性台词/OS（`{body[:12]}`），会泄掉悬念")
    if naked:
        sample = "、".join(str(n) for n in naked[:6])
        result.errors.append(f"存在 {len(naked)} 行裸叙述（非场头/△/对白），剧本不能保留小说叙述。行号：{sample}")

    duration = spoken_chars / SPEECH_CHARS_PER_SEC + action_lines * ACTION_LINE_SEC
    lo, hi = cfg["duration_range"]
    s_lo, s_hi = cfg["scene_range"]
    d_lo, d_hi = cfg["dialogue_range"]
    if not s_lo <= scenes <= s_hi:
        result.errors.append(f"场次数 {scenes}，应在 {s_lo}-{s_hi}")
    if not d_lo <= dialogue <= d_hi:
        result.errors.append(f"有效对白 {dialogue} 句，应在 {d_lo}-{d_hi}")
    if dialogue and os_lines / dialogue > cfg["os_ratio_max"]:
        result.errors.append(f"OS/旁白占对白 {os_lines}/{dialogue}，超过 {int(cfg['os_ratio_max'] * 100)}%，内心戏要外化成动作和对手戏")
    if not lo <= duration <= hi:
        result.errors.append(f"估算时长 {duration:.0f} 秒，应在 {lo}-{hi} 秒")
    if len(shot_sizes) < cfg["min_shot_sizes"]:
        result.warnings.append(f"只用了 {len(shot_sizes)} 种景别，建议至少 {cfg['min_shot_sizes']} 种")
    if first_content and "dialogue" not in first_content and "impact" not in first_content:
        result.errors.append(f"开场前 {cfg['opening_window']} 个内容行没有对白也没有特写冲击，黄金3秒不成立")

    result.metrics.update(
        scenes=scenes,
        dialogue_lines=dialogue,
        os_lines=os_lines,
        spoken_chars=spoken_chars,
        action_lines=action_lines,
        shot_sizes=sorted(shot_sizes),
        est_duration_sec=round(duration),
    )
MANJU_HEADER = ("镜号", "时长", "景别", "运镜", "画面", "台词", "音效")
ASSET_SECTION_RE = re.compile(r"^##\s*(角色与场景资产|资产表|角色资产)")
ASSET_ROW_RE = re.compile(r"^[-*]\s*\*\*([^*]+?)\*\*\s*[:：]\s*(.+)$")
LINE_SPLIT_RE = re.compile(r"[;；/]|<br\s*/?>")
SPEAKER_RE = re.compile(r"^([^：:]{1,12})[：:]\s*(.+)$")
NON_CHARACTER_SPEAKERS = {"旁白", "字幕", "画外音", "系统", "广播", "众人", "群众", "人群"}


def _split_row(line: str) -> list[str]:
    cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
    return cells


def _parse_seconds(value: str) -> float | None:
    match = re.search(r"(\d+(?:\.\d+)?)", value)
    return float(match.group(1)) if match else None


def lint_manju(text: str, result: LintResult, cfg: dict[str, Any]) -> None:
    lines = text.splitlines()
    _check_header(lines, result)
    _check_ending(text, result)

    assets: dict[str, str] = {}
    in_assets = False
    header_idx: dict[str, int] | None = None
    shots: list[dict[str, Any]] = []
    for no, raw in enumerate(lines, 1):
        line = raw.strip()
        if ASSET_SECTION_RE.match(line):
            in_assets = True
            continue
        if line.startswith("## "):
            in_assets = False
        if in_assets:
            row = ASSET_ROW_RE.match(line)
            if row:
                assets[row.group(1).strip()] = row.group(2).strip()
            continue
        if not line.startswith("|"):
            continue
        cells = _split_row(line)
        if all(re.fullmatch(r":?-{2,}:?", c) for c in cells if c):
            continue
        if header_idx is None and cells and cells[0] == "镜号":
            header_idx = {}
            for key in MANJU_HEADER:
                pos = next((i for i, c in enumerate(cells) if c.startswith(key)), None)
                if pos is None:
                    result.errors.append(f"分镜表缺少列：{key}")
                else:
                    header_idx[key] = pos
            continue
        if header_idx is None or len(header_idx) < len(MANJU_HEADER):
            continue
        get = lambda key: cells[header_idx[key]] if header_idx[key] < len(cells) else ""  # noqa: E731
        shots.append({"no": no, **{key: get(key) for key in MANJU_HEADER}})

    if header_idx is None:
        result.errors.append("未找到分镜表（表头首列必须是 `镜号`）")
        return
    if len(assets) < 1:
        result.errors.append("缺少 `## 角色与场景资产` 段，AI 出图无法锁定角色外观")
    for name, desc in assets.items():
        if len(desc) < 15:
            result.warnings.append(f"资产「{name}」外观锚点过短（<15 字），连续出图容易崩脸")

    total = 0.0
    sizes: set[str] = set()
    moves: set[str] = set()
    speakers: set[str] = set()
    s_lo, s_hi = cfg["shot_sec_range"]
    for shot in shots:
        tag = f"镜{shot['镜号']}"
        sec = _parse_seconds(shot["时长"])
        if sec is None:
            result.errors.append(f"{tag} 时长不是数字：`{shot['时长']}`")
            sec = 0.0
        elif not s_lo <= sec <= s_hi:
            result.errors.append(f"{tag} 时长 {sec}s，应在 {s_lo}-{s_hi}s")
        total += sec
        size = next((s for s in SHOT_SIZES if s in shot["景别"]), None)
        if size is None:
            result.errors.append(f"{tag} 景别非法：`{shot['景别']}`")
        else:
            sizes.add(size)
        move = next((m for m in CAMERA_MOVES if m in shot["运镜"]), None)
        if move is None:
            result.errors.append(f"{tag} 运镜非法：`{shot['运镜']}`")
        else:
            moves.add(move)
        desc = shot["画面"]
        if len(_spoken_text(desc)) < cfg["min_desc_chars"]:
            result.errors.append(f"{tag} 画面描述不足 {cfg['min_desc_chars']} 字，出图/生视频信息不够")
        if UNFILMABLE_RE.search(desc):
            result.errors.append(f"{tag} 画面写了拍不出来的心理/总结，改成表情、动作或道具")
        if INVISIBLE_RE.search(desc):
            result.errors.append(f"{tag} 画面写了看不见的东西（{INVISIBLE_RE.search(desc).group(0)}），换成可见的姿态或光")
        if GENERIC_REF_RE.search(desc.strip()):
            result.warnings.append(f"{tag} 画面用泛称开头，建议写资产表里的角色名，便于出图匹配资产")
        if MULTI_STATE_RE.search(desc):
            result.errors.append(f"{tag} 画面写了多个先后状态，一镜只能是一个定格瞬间")
        if CAMERA_IN_DESC_RE.search(desc):
            result.errors.append(f"{tag} 画面列写了运镜，运镜只写在运镜列")
        if TEXT_IN_IMAGE_RE.search(desc):
            result.errors.append(f"{tag} 画面要求画出文字，出图模型画不准汉字，改走字幕")
        if shot is shots[0] and WEAK_OPENING_RE.search(desc):
            result.errors.append(f"{tag} 首镜是起床/天气/空镜类开场，黄金3秒要直接给冲突或异常")
        if any(s in shot["景别"] for s in ("特写", "大特写")):
            regions = [name for name, words in BODY_REGIONS.items() if any(w in desc for w in words)]
            if len(regions) >= 2 and not re.search(r"前景|后景", desc):
                result.errors.append(f"{tag} {shot['景别']}里同时要拍{'和'.join(regions)}，取景框装不下，拆镜")
        spoken_total = 0
        dialogue = shot["台词"]
        if dialogue and dialogue not in {"—", "-", "无", "（无）"}:
            for part in LINE_SPLIT_RE.split(dialogue):
                part = part.strip()
                if not part:
                    continue
                spk = SPEAKER_RE.match(part)
                content = spk.group(2) if spk else part
                if spk and "画外音" in spk.group(1):
                    voice_name = re.sub(r"[（(].*?[）)]", "", spk.group(1)).strip()
                    if voice_name and voice_name in desc:
                        result.warnings.append(f"{tag} {voice_name}在画面里，台词却标画外音，配音端会混淆")
                if spk:
                    name = re.sub(r"[（(].*?[）)]", "", spk.group(1)).strip()
                    if name and name not in NON_CHARACTER_SPEAKERS:
                        speakers.add(name)
                n = len(_spoken_text(content))
                spoken_total += n
                if n > cfg["line_len_error"]:
                    result.errors.append(f"{tag} 单条台词 {n} 字，超过 {cfg['line_len_error']}，气泡/字幕放不下")
        if sec and spoken_total / sec > cfg["bubble_chars_per_sec"]:
            result.errors.append(f"{tag} 台词 {spoken_total} 字 / {sec}s，超过 {cfg['bubble_chars_per_sec']} 字/秒，观众读不完")

    for shot in shots[-4:]:
        if RELIEF_RE.search(shot["台词"]):
            result.errors.append(f"镜{shot['镜号']} 结尾钩子前出现收束性台词/OS，会泄掉悬念")

    missing = sorted(name for name in speakers if not any(name in key or key in name for key in assets))
    if missing:
        result.errors.append(f"说话角色未登记资产：{'、'.join(missing)}")

    lo, hi = cfg["duration_range"]
    sh_lo, sh_hi = cfg["shot_range"]
    if not sh_lo <= len(shots) <= sh_hi:
        result.errors.append(f"镜头数 {len(shots)}，应在 {sh_lo}-{sh_hi}")
    if not lo <= total <= hi:
        result.errors.append(f"总时长 {total:.0f}s，应在 {lo}-{hi}s")
    if len(sizes) < cfg["min_shot_sizes"]:
        result.errors.append(f"只用了 {len(sizes)} 种景别，至少 {cfg['min_shot_sizes']} 种")
    if len(moves) < cfg["min_camera_moves"]:
        result.warnings.append(f"只用了 {len(moves)} 种运镜，建议至少 {cfg['min_camera_moves']} 种")
    opening = shots[: cfg["opening_window"]]
    if opening and not any(
        ("特写" in s["景别"] or "急推" in s["运镜"] or (s["台词"] and s["台词"] not in {"—", "-", "无"}))
        for s in opening
    ):
        result.errors.append(f"前 {cfg['opening_window']} 镜没有特写冲击也没有台词，黄金3秒不成立")

    result.metrics.update(
        shots=len(shots),
        total_sec=round(total, 1),
        shot_sizes=sorted(sizes),
        camera_moves=sorted(moves),
        assets=sorted(assets),
        speakers=sorted(speakers),
    )


def lint_file(path: Path, mode: str, overrides: dict[str, Any] | None = None) -> LintResult:
    cfg = dict(DEFAULTS[mode])
    cfg.update(overrides or {})
    result = LintResult(path=str(path), mode=mode)
    try:
        text = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError) as exc:
        result.errors.append(f"无法读取：{exc}")
        return result
    if mode == "short-drama":
        lint_short_drama(text, result, cfg)
    else:
        lint_manju(text, result, cfg)
    return result


def _load_overrides(project_root: str | None, mode: str) -> dict[str, Any]:
    """读取项目 `改编/ADAPT_PROFILE.json` 中的 lint 覆盖项（可选）。"""
    if not project_root:
        return {}
    profile = Path(project_root) / "改编" / "ADAPT_PROFILE.json"
    if not profile.is_file():
        return {}
    try:
        payload = json.loads(profile.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}
    raw = (payload.get("lint") or {}).get(mode) or {}
    overrides: dict[str, Any] = {}
    for key, value in raw.items():
        if key not in DEFAULTS[mode]:
            continue
        overrides[key] = tuple(value) if isinstance(value, list) else value
    return overrides


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="短剧剧本 / 漫剧分镜格式质检")
    parser.add_argument("--mode", choices=sorted(DEFAULTS), required=True)
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument("--project-root", default=None, help="读取 改编/ADAPT_PROFILE.json 的 lint 覆盖项")
    parser.add_argument("files", nargs="+")
    args = parser.parse_args(argv)

    overrides = _load_overrides(args.project_root, args.mode)
    results = [lint_file(Path(f), args.mode, overrides) for f in args.files]
    if args.format == "json":
        print(json.dumps([r.to_dict() for r in results], ensure_ascii=False, indent=2))
    else:
        for r in results:
            status = "PASS" if r.ok else "FAIL"
            print(f"[{status}] {r.path}")
            print("  metrics: " + json.dumps(r.metrics, ensure_ascii=False))
            for e in r.errors:
                print(f"  ERROR: {e}")
            for w in r.warnings:
                print(f"  WARN : {w}")
    return 0 if all(r.ok for r in results) else 1


if __name__ == "__main__":
    try:
        from runtime_compat import enable_windows_utf8_stdio

        enable_windows_utf8_stdio(skip_in_pytest=True)
    except Exception:  # pragma: no cover
        pass
    sys.exit(main())
