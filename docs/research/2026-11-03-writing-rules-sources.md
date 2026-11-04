# 国外题材与正文语言规则：来源、证据和限制

来源读取日期：2026-11-03。读取来源时，三个题材包和两个语言包是 `1.0.0 / draft`；后续编辑框架扩展到 `1.1.0 / draft`，本记录只支撑其中明确标注的题材定义和语言惯例，不把新增账本、修订问题或初始化流程说成来源结论。国外题材 `market=overseas`；语言包 `market=shared` 只表示语言指导不绑定市场，不使旧中文 CSV 自动成为可跨市场资料。

## 实际读取与本地联网复测

先使用 web 打开一手作者、出版社、行业组织或编辑机构页面；随后从本仓库 Windows `.venv` 的 Python 3.12 用 `urllib.request` 实际 HTTPS GET，保持默认 TLS 验证，读取返回 HTML 并检查标题和正文相关段落。网络原始记录见同目录 `2026-11-03-official-source-network.json`，包含 URL、请求 UTC 时间、最终 URL、状态、标题、字节数及响应 SHA-256。

本地复测在 2026-11-03 10:49:25–10:50:52（Asia/Shanghai；02:49:25–02:50:52 UTC）完成；采用的八个页面均返回 HTTP 200。另试教育部标点手册引号页时，默认 TLS 验证报证书链错误，没有关闭证书校验重试，也没有把该页作为规则依据。第一次抓取脚本在输出含 Unicode 预览时因本机 GBK 控制台编码失败，使用 `python -X utf8` 重跑后才形成完整记录；不能把第一次输出失败误记为站点不可达。

| 来源与 URL | 实际读取部分 | 进入规则的最小结论 | 未证实事项 |
|---|---|---|---|
| Andrew Rowe 作者博客：[Progression Fantasy – A New Subgenre Concept](https://andrewkrowe.wordpress.com/2019/02/26/progression-fantasy-a-new-subgenre-concept/) | 正文定义、训练/能力发展例子、数字并非必要、与邻近类型的重叠及分类边界 | 成长奇幻把能力与技能提升作为重要叙事关注，不等同于必须有游戏界面 | 没有验证本项目长篇兑现、升级密度或任何平台偏好 |
| Aleron Kong 官方站点：[What is LitRPG?](https://www.litrpg.com/litrpgblog/2019/10/6/what-is-litrpg) | 作者自述和两项宽泛规则：明确成长、游戏型世界对故事必要 | LitRPG 的机制和成长应实际影响故事 | 该文未给 GameLit 定义；其自述销量/评价未独立核验，也未用于规则 |
| Penguin UK 出版社：[What is Romantasy? A Beginner’s Guide to the Genre](https://www.penguin.co.uk/discover/articles/romantasy-guide) | “What is romantasy”、与 fantasy/fantasy romance 的区分及常见读者入口 | 爱情与奇幻可以共同塑造人物决定和结局；先明确本书权重 | 推荐书单不是市场份额、销量或未来趋势；没有读推荐小说全文 |
| SFWA：[Romantasy: An Old Genre with a New Name](https://sfwa.org/2025/02/25/romantasy-an-old-genre-with-a-new-name/) | Rosemary Jones 正文，定义、类型历史、封面与阅读期待讨论 | 只移去爱情或只加奇幻装饰都可能改变承诺；标签有历史和读者语境 | 是作者在行业组织刊物上的讨论，不是组织发布的统一写作标准；文中未定义 HEA/HFN 缩写 |
| Romance Writers of America：[Proof of Serious Pursuit](https://www.rwa.org/proof-of-serious-pursuit) | 正文脚注的 Romance fiction 定义 | 类型 Romance 以核心爱情故事和情感满足且乐观的结局为期待，因此初始化必须问清结局 | 会员条件不适用于本项目；不能由此断言所有称作 romantasy 的作品都遵循同一结局 |
| W3C Chinese Layout Task Force：[Requirements for Chinese Text Layout](https://www.w3.org/International/clreq/) | 文档范围、地区/简繁差异、标点及中西文混排段落；未通读全部附录 | 中文排版存在地区、样式与横竖排选择，语言包应允许项目明确样式 | 访问时为编辑草稿、未获 W3C 会员认可；不把它当正式标准，也不据此规定小说句长或爽点 |
| CMOS Shop Talk：[Is a Comma Needed to Introduce Dialogue?](https://cmosshoptalk.com/2022/11/08/is-a-comma-needed-to-introduce-dialogue/) | 正文区分说话标签、句内引语和句法原因；含创作例外讨论 | 英文对白标点应按句法和项目样式处理，不按 said 标签比例删改 | 不是完整英文编辑，也不是所有出版社唯一惯例 |
| CMOS Shop Talk：[Formatting Thoughts in Fiction](https://cmosshoptalk.com/2020/08/18/formatting-thoughts-in-fiction/) | 正文对直接/间接思想、斜体、引号和人称变化的示例 | 内心呈现可有多种惯例，选择应与 POV、距离及项目样式一致 | 没有证明一种样式适合全部题材；付费手册本体未读取 |

未采用的网络尝试：[教育部《重訂標點符號手冊修訂版》引号路径](https://language.moe.gov.tw/001/Upload/FILES/SITE_CONTENT/M0001/HAU/h7.htm)。本地 TLS 失败记录仅证明此次客户端请求未成功，不推断网站停机、页面不存在或其正文内容。

## 从来源到规则的编辑判断

来源直接支撑的是有限的定义或表达惯例。初始化问题、卷纲流程、规则账本、关系自主性检查、具体原创微例，以及事实/语言分离策略，都是本项目为实现用户需求制定的编辑方案，并非逐项摘自资料。没有采用国内模板翻译成英文，也没有把作者个人定义改称跨平台统一规范。

题材包只定义读者承诺和可讨论的写法；语言包处理表达、术语与项目样式。`zh` 包保持市场中立，不包含 40 字拆句、固定短句比例、固定爽点次数、固定对白标签比例或固定起冲突窗口。国外中文与国外英文共用国外题材包，管理说明和中文路径保留。

`allow_draft_rules=true` 是国外 draft 题材的显式试用门槛。语言包均保留 draft 状态并按固定版本加载，作为表达建议，不给国内中文初始化追加试用要求。读取来源与 JSON/helper 校验都不能把 draft 升级为 supported。升级证据仍缺：足量完整章节、跨章成长/数值/关系连贯审查、英语母语编辑、目标读者反馈和具体平台样式验证。

## 样章与自动化是不同证据

第一轮原创短样章在 `writing-rule-samples/`；逐段自行阅读观察在 `2026-11-03-writing-rule-sample-quality.md`。这些是本次助手写出并自行复核的文本，不是独立人类编辑或外部评委结论。第二轮较长的跨章案例与模型交叉审读另记于 `overseas-quality-round2/README.md`，两轮都没有英语母语编辑、平台投稿、A/B 读者测试或商业样章验证。

运行时、配置、合同、计数、提交和 Dashboard 的自动检查由主任务另外记录；这里不借用它们的通过结果宣称文学质量通过。已知 Windows 基线的覆盖率门槛问题也不能由短样章观察抵销。
