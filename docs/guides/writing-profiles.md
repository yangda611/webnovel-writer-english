# 市场、正文语言与题材配置

交互和管理说明默认中文，正文语言单独选择。第一版国外市场指英语读者，平台可留空。内部路径仍为 `正文/`、`大纲/`、`设定集/`。

| 市场 | 正文 | 题材规则 | 章长及进度单位 |
|---|---|---|---|
| 国内 domestic | 中文 zh | 原国内模板与知识范围 | characters（字） |
| 国外 overseas | 中文 zh | 国外规则包 | characters（字） |
| 国外 overseas | 英文 en | 同一国外规则包 | words（词） |

`/webnovel-init` 的采集顺序为：国内／国外 → 国外正文中文／英文 → 主辅题材 → 原有分步问答。国内默认中文。首批国外包为 `progression_fantasy`（成长奇幻）、`litrpg`、`romantasy`（奇幻言情）。主类型优先定义读者承诺，辅类型全部保存；未知辅类型会报错。

这些国外包当前均为 **draft 试用**。读取来源不代表已经过目标平台、母语编辑或长篇读者验证。显式选择试用时使用 `--allow-draft-rules`；不声称正式支持。

## Windows 本地示例

在仓库根目录配置 `.venv` 后，通过统一入口初始化。将目标路径换成自己的书项目目录：

```powershell
.\.venv\Scripts\python.exe -X utf8 .\webnovel-writer\scripts\webnovel.py init "E:\books\桥之誓" "桥之誓" "progression_fantasy+litrpg" --market overseas --body-language zh --chapter-length 3000 --allow-draft-rules
.\.venv\Scripts\python.exe -X utf8 .\webnovel-writer\scripts\webnovel.py init "E:\books\Bridge" "Bridge" "progression_fantasy" --secondary-genre litrpg --secondary-genre romantasy --market overseas --body-language en --chapter-length 2000 --pov third_limited --tense past --protagonist-name "Maeve O’Connell" --allow-draft-rules
```

`--chapter-unit` 通常省略，程序按正文语言校验。总规模兼容参数 `--target-words` 同样使用该项目单位。未定平台无需传 `--platform`。

查看并验证配置和完整规则包：

```powershell
.\.venv\Scripts\python.exe -X utf8 .\webnovel-writer\scripts\writing_profile.py --project-root "E:\books\Bridge" --bundles
```

## 配置与合同

`.story-system/WRITING_PROFILE.json` 是持久配置来源，包含市场、正文语言、主辅题材、章长和单位、各包版本及可选 POV／时态／平台。`state.json` 的同名字段只作展示快照。

合同保存配置相对路径、SHA-256 指纹和包版本。刷新合同会保留初始化选择及手工约束；写前检查会拒绝缺失或过期的绑定。不要仅修改 state 快照来切换市场或语言，也不要把其他项目的合同直接复制来继续写章。第一版不提供在已写项目中自动转换市场、语言或包版本的迁移工具。

重复初始化同一项目会保留已有配置、正文、设定与进度；只传原主题材时也保留已有辅类型。显式传入不同选择会报错。完全没有新配置或引用的旧项目保持国内中文旧行为，不会自动写入新配置；已存在新配置标记的项目一旦配置丢失或损坏，则明确报错。

## 检索与审查

旧 CSV 未标注市场的条目归国内，即使写着“适用题材＝全部”。共享条目必须显式标记 `market=shared` 和 `human_reviewed=true`。检索先隔离市场范围，再匹配题材、技能和查询内容。

国外中文与国外英文共用题材包，分别加载中文／英文表达包。中文表达包不默认要求国内爽点密度、句长或固定反转周期。事实 reviewer 保持原有五维职责；语言和审美建议单独呈现，不自动成为事实阻断。

## 计量与验证边界

兼容字段 `word_count`／`total_words` 保留，另带 `count_unit`。中文沿用去除章级 Markdown 标记后字符长度的口径；英文使用统一 Unicode 词元策略，缩写、内部撇号和连字符有明确定义。正文文件、提交投影、数据库、报告和面板使用同一计量函数。重复投影不重复累计。

`The old bridge crossed the river beneath a pale sky.` 原始文本有 52 个字符，英文计数为 10 词。

自动化链路测试验证配置、合同、提交、记忆与投影的行为。样章的文学质量和读者适配另行记录；链路通过不能替代母语编辑或真实读者评估。实际本地测试结果见 `docs/operations/` 中本次验证记录，来源和样章评估见 `docs/research/`。
