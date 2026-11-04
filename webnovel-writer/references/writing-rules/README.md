# 市场、正文语言与规则包加载契约

本目录是版本化规则资料，不是正式平台认证。`genres/` 首批三个国外题材及 `languages/zh.json`、`languages/en.json` 的当前版本为 `1.1.0` / `draft`，每个 `1.1.0` 包均有同内容固定快照。旧 `1.0.0` 包按原字节保存在 `versions/{genres,languages}/{id}/1.0.0.json`；显式版本只从对应归档读取，归档缺失或损坏就报错，不能退回可变当前包。现有项目继续按配置钉住的版本读取，不静默升级。实际读取一手来源只证明研究过程；第一轮短样章观察见 `docs/research/2026-11-03-writing-rule-sample-quality.md`，本轮连续样章和交叉审查见 `docs/research/overseas-quality-round2/`。它们可以揭示个案矛盾和编辑取舍，不能替代英语母语编辑、目标平台或读者群验证。

## 所有创作入口先读统一配置

初始化已有项目、规划、上下文压缩、起草、润色、审查与创作参考检索，都先读取项目 `.story-system/WRITING_PROFILE.json`，然后运行：

```bash
python -X utf8 "${SCRIPTS_DIR}/writing_profile.py" --project-root "${PROJECT_ROOT}" --bundles
```

使用 helper 返回的验证后配置与 `genre_rules` / `language_rules`；记录市场、正文语言、主类型、**全部**辅类型、章长/单位、POV、时态、平台、规则包版本及配置指纹。`state.json` 的快照只作展示，不能反过来覆盖配置或固定包版本。合同引用与配置不符时先报错，不能继续写章或靠刷新清空用户设定。

- `domestic + zh`：保留国内兼容链；仅纯旧项目允许 helper 判定为 legacy。新配置损坏、被删而 state/合同仍有国外标记时不得回落。
- `overseas + zh`：加载全部已选国外题材包与市场中立的 `zh` 包。管理说明仍用中文。
- `overseas + en`：加载全部已选国外题材包与 `en` 包。正文直接用英文组织；交互、大纲管理、审查说明仍用中文。
- `domestic + en`：第一版不支持，明确报错，不自动改市场或语言。

国外所选题材包是 draft 时，必须有项目显式 `allow_draft_rules=true` 才能试用这些题材规则。两个市场中立语言包也保留 draft 与固定版本，但作为表达建议展示，不因此对新旧国内中文项目追加试用闸门；语言建议不代表市场认证。已有授权持续有效，不重复询问。国外题材无授权时只解释试用范围并请作者选择，禁止悄悄改标记或把 draft 写成正式支持。未知主/辅类型逐项报错并保留原输入，禁止丢弃第三个以后的辅类型、截断、自动映射到仙侠或强行替换成已知类型。

## 国外入口的参考隔离

国外项目只把 helper 输出的国外题材包与对应语言包作为写法默认。国内 `genre-profiles.md`、`templates/genres/`、国内反套路库、`cool-points-guide.md`、`strand-weave-pattern.md`、`reading-power-taxonomy.md` 及旧节奏/网文化/Anti-AI 参考，不得以 `always`、找不到就加载或“全部”的方式进入国外上下文。结构化时间、因果、节点和文件格式可以沿用，但读取时只取结构段，不连带加载这些文件里的国内商业节拍。

已有作者自定文风契约可继续使用；若它与本次配置或用户要求冲突，列出具体冲突。不得把自动生成的国内旧默认伪装成作者约定。

创作 CSV 检索必须带项目根以便执行市场隔离：

```bash
python -X utf8 "${SCRIPTS_DIR}/reference_search.py" --project-root "${PROJECT_ROOT}" --skill {init|plan|write|review|query} --table "{表名}" --query "{关键词}" --genre "{主类型}"
```

需要辅题材时逐项检索并标明来源；不使用主类型重建来替换配置中的辅类型。旧中文 CSV 未标市场按 domestic；只有显式人工审阅为 shared 的条目可跨市场。国外无结果时返回“当前无适用资料”，继续使用已加载的包，禁止改用 `全部`、shuangwen、修仙或国内命名模板补齐。

## 规划、起草、润色与审查的分工

- 规划消费题材包 `reader_promise`、`init_questions`、`outline_guidance`，根据本书承诺安排节点，不规定固定章长窗口、爽点密度或高潮间隔。管理大纲保留中文，文件仍放 `大纲/`、`设定集/`。
- 起草消费全部题材包 `writing_guidance` 和对应语言包 `expression_guidance`。章长与单位取配置；英文以 words 计，不套用 40 字拆句、200–400 字起冲突等中文阈值。
- 润色先处理已报告事实问题，再以语言包检查指代、POV、时态、术语、对白标点和场景可读性。国外项目不加载国内固定词频、said 标签比例、短句占比或固定改写次数。发现语言问题时给具体改写与理由，不推断“AI 率”。
- `reviewer` 的 `setting / timeline / continuity / character / logic` 五维和既有 blocking 证据门槛保持不变。规则包的 `fact_checks` 可帮助定位证据；`advisory_checks` 由主流程单独写中文建议，不进入 reviewer JSON 或事实 metrics，不自动阻断 CHAPTER_COMMIT。

国外润色报告可以给 `language_advisory`（建议、位置、理由、可选改写）。语言终检不能伪装成事实审查；若现有流程保留 `anti_ai_force_check` 展示字段，明确标注它仅是编辑记录、不是国外事实提交闸门。作者要求的特殊文风也不能解除事实冲突。

## 证据与升级

JSON 的 `sources` 保存 URL、标题、访问日期、实际读取范围和限制。`examples` 为本项目原创微例，不摘录在售小说，也不是把国内模板翻译后贴上英文标签。来源更新不自动更改项目固定版本；发布新版本前需另外记录完整样章、事实/语言分离的审查和目标读者反馈。任何平台适配、商业质量或英文母语自然度结论都不能仅由 helper 或 JSON 校验给出。

`1.1.0.editorial_framework` 增加 primary/secondary 应用、跨场景/章/卷承诺问题、事实账本、场景复核问题及原创弱/强对照。已读来源支撑类型范围与边界；这些工具是明确标注的项目编辑方案，不声称来自官方定义，也不代表读者偏好验证。`editorial_guidance` 通过运行时和合同展示建议，不进入事实 reviewer blocking。旧 `1.0.0` 包没有该字段时仍可加载，运行时会用原有 reader promise 兼容展示。
