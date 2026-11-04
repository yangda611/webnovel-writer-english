# 国内／国外题材与正文语言扩展 Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement this plan task-by-task. Independent rule research and measurement work may use superpowers:dispatching-parallel-agents. Finish with a fresh independent diff review.

**Goal:** 在 Windows 本地打通国内中文、国外中文、国外英文三种组合，保留现有事实、事件、提交、记忆与投影核心。

**Architecture:** `.story-system/WRITING_PROFILE.json` 是唯一持久配置，state 仅保存快照。题材包与语言包独立、版本固定；合同携带配置指纹，运行时和写前检查拒绝不匹配。缺少新配置的纯旧项目继续走国内旧链；显式新项目损坏时不得静默降级。

**Tech Stack:** Python 3.12、Pydantic 2、pytest/coverage、SQLite、FastAPI、Node.js 22、React/Vite。

**Spec:** 本次用户完整需求；下列约束是其仓库内记录，不依赖云端交接文件。

## Global Constraints

- 市场 `domestic|overseas` 与正文语言 `zh|en` 独立；第一版不支持国内英文。交互和管理说明默认中文。
- 保留 `正文/`、`大纲/`、`设定集/` 等中文目录和文件名。
- 首批国外题材 `progression_fantasy`、`litrpg`、`romantasy`；主辅全部保留；未知辅类型报错。
- 资料未核实保持 draft；draft 可显式选择试用，不宣称正式支持；记录实际读取来源及核实边界。
- 包含市场、语言、主辅类型、章长/单位、规则包版本、语言包版本、可选 POV/时态/平台。
- 旧中文 CSV 无市场标注默认 domestic；shared 需要显式人工审阅标志。
- 事实 reviewer 五维职责不变；语言、节奏、审美建议独立且不自动事实阻断。
- 不重置用户文件；重复初始化保留配置及正文；冲突显式报错。
- 根 `requirements.txt` 安装依赖，前端 `npm ci`；完整 pytest 保持 90% 覆盖门槛，不跳过失败来宣称通过。
- 历史 Linux 798 passed/1 skipped/88.76% 仅作背景，重新记录本地 Windows 基线。

## Review Focus

1. 配置删除/损坏、state 和合同仍有国外标记：拒绝回落。
2. 第三个或未知辅类型、别名与英文姓名：全部保留或明确拒绝，禁止截断。
3. 合同刷新/重复初始化/包升级：用户内容和固定版本不得丢失，过期合同不能写章。
4. 英文缩写、连字符、数字、Markdown 标题：统一计数策略；重复投影不累计，修订按当前 accepted 章节重算。
5. 国外上下文所有入口：旧“全部”、中文固定句长、shuangwen/修仙 fallback 不得混入。

## 本地审计起点

- HEAD `b38056e`，分支 master，起始 Git 状态干净；未发现适用 AGENTS.md 或交接文件。
- Node v22.23.4/npm 10.9.9；初始仅 Python 3.14，准备安装 3.12。
- 已复核：init 和 engine 拒绝 ASCII 题材，西幻→xianxia，ContextManager 主类型重建和截断，ContractMeta 缺少配置字段，MASTER_SETTING 每次重写，多个字符计数入口。

## 公共接口（跨任务固定）

`data_modules/writing_profile.py` 提供：

- `WritingProfile`（Pydantic）：`schema_version=1`, `market`, `body_language`, `primary_genre`, `secondary_genres: list[str]`, `chapter_length`, `chapter_unit: characters|words`, `rule_pack_versions: dict[str,str]`, `language_pack_version`, `pov`, `tense`, `platform`, `allow_draft_rules=False`。
- `build_writing_profile(*, market='domestic', body_language='zh', genre, secondary_genres=None, chapter_length=None, chapter_unit=None, pov=None, tense=None, platform=None, allow_draft_rules=False) -> WritingProfile`。
- `load_writing_profile(project_root: Path, *, state=None) -> WritingProfile`：验证文件和包；纯旧项目返回国内兼容配置。
- `save_writing_profile(project_root, profile) -> None`：原子写入，已有不同配置拒绝覆盖。
- `profile.to_snapshot() -> dict`，`profile.reference() -> dict`：包含相对配置路径、sha256 指纹及各包版本；兼容旧项目引用标明 legacy。
- `load_rule_bundles(profile) -> dict`：`genre_rules`（列表）与 `language_rules`（对象）；国内用旧模板显式命名空间，国外只加载国外包。

规则文件位于 `webnovel-writer/references/writing-rules/{genres,languages}/<id>.json`，含 `id/version/status/market`、`reader_promise/scope/init_questions/outline_guidance/writing_guidance/review_focus/examples/sources`；语言包另含 `body_language` 和表达指导。版本初值 `1.0.0`，资料证据不能替代样章验证。

### Task 1: 环境和可回放基线

- [x] 检查 Git/AGENTS/依赖；在当前 checkout 建 `codex/market-language-profile`，不另搬工作区。
- [x] 安装 Python 3.12，创建忽略的 `.venv`，从根 requirements 安装；前端 npm ci。
- [x] 跑完整 pytest，记录真实 Windows 结果（包括既存失败和覆盖率）；不调整阈值。

### Task 2: 统一配置、注册和初始化

**Files:** `scripts/data_modules/writing_profile.py`, `scripts/data_modules/rule_registry.py`, `scripts/init_project.py`, `scripts/genre_taxonomy.py`, `scripts/data_modules/genre_aliases.py`, 对应新测试。

- [x] 先写配置三组合、严格校验、未知辅类型、全部辅类型保留、缺损/版本错配、重复初始化回归并观察失败。
- [x] 实现上述公共接口，主辅别名逐项解析，国外与国内注册隔离；修正西幻别名。
- [x] init 增加市场/语言/章长/单位/辅类型/POV/时态/draft 参数；保留已有配置和内容，冲突拒绝。
- [x] 国外初始化不用旧国内模板；保持中文目录与管理结构；保存配置引用和展示快照。
- [x] 跑相关测试到通过。

### Task 3: 规则研究与工作流说明

**Files:** `references/writing-rules/`, `skills/webnovel-{init,plan,write,review}/`, `agents/`, `docs/research/`。

- [x] 本地重新联网，实际读取第一方作者/出版社/行业组织来源，保存来源证据与适用边界。
- [x] 编制三个国外包和 zh/en 语言包，读者承诺到示例齐全，未充分验证保持 draft。
- [x] 初始化菜单顺序为市场→国外正文语言→主辅类型→原问答；国内默认中文。
- [x] 修改大纲/起草/润色/审查/检索加载；海外不加载国内固定节奏；事实审查与语言建议分开。
- [x] 记录中英文原创短样章逐段质量观察，明确同一助手自评，和自动链路验证分开。

### Task 4: 统一计数、提交投影和 Dashboard

**Files:** 新 `scripts/data_modules/text_metrics.py`；state/index projection、commit、status_reporter、dashboard 相关文件及测试。

- [x] 先写英文 10 词、中文兼容、缩写/连字符/数字、投影幂等和状态/数据库/面板一致测试并观察失败。
- [x] `count_text(text, body_language='zh') -> int`：中文保持旧字符口径，英文使用公开定义的 Unicode 单词策略；统一计量单位，避免信任错误旧计数。
- [x] `word_count` 和 `total_words` 兼容字段保留，显式携带单位；accepted commit 与投影统一计数，重放不累计。
- [x] 状态报告、上下文进度和 Dashboard 标签及图表单位统一；前端 build。

### Task 5: 合同、运行时、上下文、知识隔离与写前检查

**Files:** `scripts/story_system.py`, `scripts/reference_search.py`, `data_modules/{story_system_engine,story_contract_schema,story_contracts,runtime_contract_builder,story_runtime_sources,context_manager,preflight,...}.py` 及测试。

- [x] 先写国外隔离、中文全部默认 domestic、shared 人工审阅、合同配置指纹过期、刷新保留、主辅不丢失测试并观察失败。
- [x] engine 从配置加载题材/语言包；ContractMeta 显式声明 profile 引用/版本；MASTER_SETTING 刷新保留配置约束。
- [x] Runtime/Context 直接读取统一配置；国外不调用 legacy guidance/fallback；超过两个辅类型不截断。
- [x] 检索先按 market/shared 审阅状态隔离，再按 skill/genre/task 搜索；CLI 接受项目配置。
- [x] 写前拒绝缺损/版本不符/指纹过期合同；不改变事实五维阻断职责。

### Task 6: 集成验证和独立差异审查

- [x] 三组合各实际初始化→配置→合同刷新→上下文→写前→提交→重复投影；包含英语人名、别名、机器字段。
- [x] 完整 Windows pytest 和覆盖率，前端 npm build；按失败根因补回归，不降低 90%。
- [x] 独立 reviewer 只读审查完整差异、计划与证据；修复重要问题并重跑必要检查。
- [x] 在 `docs/operations/` 写本地验证结果、样章质量边界、draft 状态与待办；最终说明实际结果。

## 执行记录

记录每项完成证据、偏差和审查结论；计划已由本次明确实施指令授权，按本地会话持续执行，不另设方案确认停点。用户要求当前仓库实施，因此保留当前 checkout，在功能分支工作。


### 完成证据（2026-11-03）

- Python 3.12.10／Node 22.23.4，根 `requirements.txt` 安装、前端 `npm ci` 完成。Windows 原始基线 799 passed、88.77%（既有覆盖门槛未通过），不是历史 Linux 结果。
- 三组合公开 CLI 与完整配置→合同→上下文→写前→事实提交→记忆/状态/索引→重放链路完成；主辅不截断，重复初始化逐字节保护。合同刷新会从 profile 修复主合同配置，同时保留作者自定义约束。
- 最终 Windows pytest 为 971 passed、0 failed、0 skipped、1 warning；11,599 statements / 10,459 covered，90.17%，既有 90% 门槛通过。前端 build、插件 strict（0 errors/0 warnings）和 `git diff --check` 通过。
- 独立只读差异审查未发现剩余可复现问题。审查发现的问题均先添加回归测试再修复；最终差异检查后新增的测试夹具变更已再次通过完整套件。
- 五个规则包仍为 1.1.0 draft；国外题材显式试用，语言包是独立表达建议。本地重新尝试读取来源页面，其中八页实际检查标题，另有 TLS 失败页未作为核实依据；来源可达性不代表市场或文学质量验证。
- 四组共八章连续原创案例分别通过合同和投影链路，并经独立模型交叉审读；事实审查与语言/审美建议分开记录。没有母语编辑、目标读者或平台验证，不宣称文学质量认证。
- 国内题材身份采用注册 label，模板独立解析，避免玄幻/仙侠共用模板而丢失；accepted 计量快照独立于未验收文件编辑；合同约束保护覆盖四层指定人工容器。
- 完整验证、运行命令、失败中间运行说明与保留边界见 `docs/operations/2026-11-03-writing-profile-validation.md`。变更留在功能分支，未提交/推送。
