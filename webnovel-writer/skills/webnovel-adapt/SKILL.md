---
name: webnovel-adapt
description: 把已写好的小说章节改编成竖屏短剧剧本或漫剧（动态漫/AI 漫剧）分镜脚本，含分集规划、格式质检、改编审查与迭代改写。
allowed-tools: Read Write Edit Grep Bash Agent AskUserQuestion
argument-hint: "--mode short-drama|manju [章号或范围，如 4 或 1-10] [--episodes N]"
---

# 小说改编：短剧剧本 / 漫剧分镜

## 目标

把 `正文/` 里已接受的章节改编成可直接进入制作的单集文件：

- `--mode short-drama`：竖屏真人短剧剧本，输出到 `改编/短剧/第{NNN}集-{标题}.md`
- `--mode manju`：漫剧分镜脚本（含角色资产表），输出到 `改编/漫剧/第{NNN}集-{标题}.md`

同时维护 `改编/改编说明.md`（分集对照与改动记录）和 `改编/ADAPT_PROFILE.json`（改编配置）。

本 skill **只读** 原著正文、设定集、大纲和 `.webnovel/summaries/`，不写 `.webnovel/`、`.story-system/`、`正文/`、`设定集/`、`大纲/`，不触发 chapter-commit。改编产物不进入原著事实链。

## 参考资料（按步骤读取）

| 步骤 | 文件 | 读取方式 |
|------|------|----------|
| Step 2-3 | `references/adaptation-craft.md` | 全文 |
| Step 3 | `references/short-drama-format.md`（short-drama）或 `references/manju-storyboard-format.md`（manju） | 全文 |
| Step 4 | 同上格式文件 | 按 lint 报错定位段落 |

## 硬规则

- 改编不改原著事实：人物关系、设定、战斗/事件结果、角色知识边界、伏笔揭露时机都以原著为准。需要新增或改动的地方写进 `改编/改编说明.md` 的"改编改动"段。
- 每集必须先通过 `adapt_lint.py`（Step 4），再交给 `adapt-reviewer`（Step 5）。lint 不通过不得送审。
- 必须用 `Agent` 工具调用 `webnovel-writer:adapt-reviewer`；主流程不得自己给分。
- 质量门槛：每集 `adapt-reviewer` 总分 ≥ 90/100，且没有任何单项低于该项满分的 70%，且 `blocking_issues` 为空。达不到就按审查意见改写，再 lint、再审，**最多 3 轮**。3 轮后仍不达标，停下来用 `AskUserQuestion` 让作者裁决（接受当前版本 / 手动修改 / 放弃本集）。
- 不覆盖作者手改过的改编文件：目标文件已存在且不是本次会话生成的，先询问。

## 执行流程

### Step 0：环境

```bash
export WORKSPACE_ROOT="${CLAUDE_PROJECT_DIR:-$PWD}"
export SCRIPTS_DIR="${CLAUDE_PLUGIN_ROOT:?}/scripts"
export SKILL_ROOT="${CLAUDE_PLUGIN_ROOT:?}/skills/webnovel-adapt"
export PROJECT_ROOT="$(python -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${WORKSPACE_ROOT}" where)"
```

解析失败时，若用户直接给了正文文件路径，可以把该文件所在书项目根当作 `PROJECT_ROOT`（只需有 `正文/`）。

### Step 1：改编配置

读取 `改编/ADAPT_PROFILE.json`；不存在则用 `AskUserQuestion` 一次问完（每题给推荐项，用户说"默认"就按推荐）：

1. 模式：短剧 / 漫剧（参数已给则跳过）
2. 原著范围：第几章到第几章（参数已给则跳过）
3. 单集时长：短剧 90-150 秒（推荐 120）；漫剧 60-120 秒（推荐 90）
4. 漫剧画风（仅 manju）：如"国风热血少年漫，厚涂"
5. 改编强度：忠实（只做格式转换和必要外化）/ 短剧化（推荐：加压冲突、加狠台词、调整揭露顺序，不改事实）

写入：

```json
{
  "mode": "short-drama",
  "source_chapters": [1, 10],
  "episode_target_sec": 120,
  "style": "",
  "intensity": "dramatized",
  "lint": {"short-drama": {}, "manju": {}}
}
```

`lint` 里可覆盖 `adapt_lint.py` 的默认阈值，例如 `{"short-drama": {"duration_range": [60, 90]}}`。

### Step 2：读原著并拆集

1. 读取范围内的正文章节、相关 `.webnovel/summaries/chNNNN.md`、`设定集/` 中出场角色和世界观，以及大纲中与这些章节相关的段落。
2. 按 `adaptation-craft.md` 第二节拆集。列出每集：原著来源（章 + 段落）、主爽点、结尾钩子、是否付费卡点。
3. 写入或更新 `改编/改编说明.md` 的"分集对照"。
4. 范围超过 3 章时，先把分集表给作者看一眼再写（用户已说"直接写"则跳过）。

### Step 3：逐集起草

对每一集：

1. 只依据本集对应的原著段落、设定和上一集结尾钩子起草。
2. 严格按格式文件输出；短剧不能出现裸叙述行，漫剧必须有资产表。
3. 第 2 集起，开头 15 秒（漫剧前 3-5 镜）先回应上一集钩子。
4. 写入目标文件。

### Step 4：格式质检（确定性）

```bash
python -X utf8 "${SCRIPTS_DIR}/adapt_lint.py" --mode {mode} --project-root "${PROJECT_ROOT}" --format json "{episode_file}"
```

有 `errors` 就按报错改到通过，然后重跑。`warnings` 尽量处理，不强制。

### Step 5：改编审查（评分）

同一份稿子**并行调用两次** `adapt-reviewer`（两个独立的 Agent 调用，放在同一条消息里），分别写入 `改编/审查/第{NNN}集-第{R}轮-a.json` 和 `-b.json`。然后合并：

```bash
python -X utf8 "${SCRIPTS_DIR}/adapt_score.py" "改编/审查/第{NNN}集-第{R}轮-a.json" "改编/审查/第{NNN}集-第{R}轮-b.json" --out "改编/审查/第{NNN}集-第{R}轮.json"
```

`adapt_score.py` 会核对每份 JSON 的扣分明细与分数是否一致，并按维度取两份的平均分。两份总分相差超过 8 分时，它会提示分歧；这时再调用第三次 `adapt-reviewer`，三份一起合并（取中位数）。改写只采纳**两份审查都提到**的问题，以及任何一份提出的 `blocking_issues`。

Use the Agent tool to run `webnovel-writer:adapt-reviewer`.

Task:
- mode={mode}
- episode_file={episode_file}
- source_files={本集对应的原著章节路径，逗号分隔}
- setting_files={相关设定集路径}
- previous_episode_file={上一集路径，第一集为空}
- project_root=${PROJECT_ROOT}
- 只返回 adapt-reviewer schema JSON，不写文件。

主流程把返回 JSON 写到 `改编/审查/第{NNN}集-第{R}轮.json`（R 为轮次）。

### Step 6：迭代

- 达到 Step 0 硬规则的质量门槛 → 本集通过，进入下一集。
- 未达到 → 按 `blocking_issues` 和每项 `fix` 定点改写（改动多时可以重写整集），回到 Step 4。轮次 +1。
- 第 3 轮仍未达到 → `AskUserQuestion` 裁决。

一集通过后，把本轮发现的**可复用**问题（同一类错误出现两次以上）追加到 `改编/改编说明.md` 的"写作提醒"段，后续集起草前先读这一段，避免重犯。

### Step 7：收尾报告

用中文向作者报告：

```text
总状态：已完成 / 部分完成 / 需要你处理。

一、产出
- 改编/短剧/第001集-xxx.md  得分 93（2 轮）
- ...
- 改编/改编说明.md

二、需要你确认的改编改动
- 第3集：……

三、下一步
- 继续改编：/webnovel-adapt --mode short-drama 11-20
```

不输出原始 JSON。分数只是审查 agent 的编辑判断，不代表平台数据或真实完播率，报告里要说明这一点。
