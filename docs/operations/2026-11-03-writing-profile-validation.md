# 国内／国外题材与正文语言：Windows 本地验证

验证日期：2026-11-03（Asia/Shanghai）。仓库 `yangda611/webnovel-writer-english`，起点 `b38056e`，功能分支 `codex/market-language-profile`。开始时工作区干净，未发现适用 `AGENTS.md`；本次不依赖云端交接文件，没有重置仓库或推送变更。

## 环境与结果

Python 3.12.10，Windows 本地 `.venv`，依赖从仓库根 `requirements.txt` 安装。Node.js v22.23.4／npm 10.9.9，前端按现有锁文件 `npm ci`。

| 检查 | 实际结果 |
|---|---|
| 修改前 Windows 完整基线 | 799 passed；覆盖率 88.77%，因既有 90% 门槛退出失败 |
| 本轮最终完整 pytest | **971 passed，0 failed，0 skipped，1 warning**；31.07 秒 |
| 本轮最终覆盖率 | **90.17%**；11,599 条语句，1,140 未覆盖；90% 门槛通过 |
| 前端 `npm run build` | 成功，674 modules；保留 ECharts 大包体积提示 |
| 实际插件包 `validate_plugin_package.py --strict` | 成功，0 errors、0 warnings |
| 真实样章链路 | 四组连续样章均通过合同、写前、提交、投影、Dashboard、计量和重复初始化链路；另记录叙事审读结果 |
| `git diff --check` | 通过；Git 仍提示部分文件的 LF／CRLF 转换 |
| 独立差异审查 | 初始化恢复和主合同路由一致性缺口均已补测试修复；最终只读复核未发现剩余可复现缺陷 |
| 真实公开 CLI 冒烟 | 三组合各初始化、读取完整 bundles、重复初始化成功；辅题材均保留 |

此前 941 passed / 90.12% 和 970 passed / 90.18% 分别是较早代码快照结果；当前最终结果为 971 passed / 90.17%，包含主合同路由一致性回归测试。

最终完整测试命令在仓库根执行：

```powershell
$env:PYTHONUTF8 = '1'
.\.venv\Scripts\python.exe -m pytest -o addopts='-p no:debugging -p pytest_cov -p no:cacheprovider' -q --cov --cov-report=term-missing --cov-report=json:.tmp_coverage_final.json --cov-fail-under=90 --junitxml=.tmp_validation_final.xml
```

`-o addopts` 只展开现有插件设置，避免仓库配置与命令重复 `-q` 隐藏汇总；测试目录和 90% 阈值没有改变，没有排除用例。生成的本地日志、JUnit 和覆盖率文件属于忽略的临时产物；可持久核对的汇总见同目录 `2026-11-03-writing-profile-results.json`。

较早的第一次全量运行只给 pytest 父进程加 `-X utf8`，子进程仍默认 GBK，导致既有 CSV 子进程测试文本解码失败；最终命令使用可继承的 `PYTHONUTF8=1`，没有跳过或排除用例。当前全量结果的单条汇总 warning 来自 Starlette/httpx 兼容提示。

## 需求与验证证据

| 需求 | 验证方式与结论 |
|---|---|
| 国内中文、国外中文、国外英文 | `test_writing_profile.py`、`test_init_writing_profile.py`、`test_writing_profile_chain.py`；公开 CLI 另行生成真实临时书项目并读取 helper |
| 主辅全部保留，未知辅类型报错 | 测试三个题材、重复别名、未知辅类型及包含已知名称的未知字符串；国内玄幻／仙侠即使共用模板也保持独立标识 |
| 国外不混国内默认规则 | 国外 engine/context 只读全部国外包和对应语言包；CSV 未标市场含“全部”仍默认国内，shared 必须显式人工审阅 |
| 重复初始化保护 | 对配置、正文、设定、进度做逐字节前后比较；旧 `project.title` 结构同样识别；正文或 MASTER_SETTING 存在但身份缺失时拒绝重新初始化；显式合同缺失可恢复，指纹冲突在写入前拒绝 |
| 配置严格校验与合同保留 | 缺失、损坏、未知字段、错误单位、包版本错配、孤立子合同／commit 都有回归；四层合同刷新保留指纹和固定版本 |
| 过期合同不能绕过提交 | 写前、precommit、accepted build/apply 均校验；四层缺失、任一过期、旧配置排队提交在事件写入前拒绝 |
| 人工覆盖约束不丢 | MASTER 手工约束保留；chapter `override_allowed` 与 volume/review 的 `overrides` 受保护；绑定或 locked 冲突在相关 JSON 写入前拒绝 |
| 字符／英文词数统一 | 用户示例 52 characters／10 words；统一 Unicode 单词策略覆盖撇号、连字符、缩写、组合标记与数字；中文保持原字符与 Markdown 过滤口径 |
| 状态、DB、报告、面板一致 | 三组合对照 commit/state/index/Dashboard/report/context；手工 index API/CLI 也依据权威配置重新计量，失败时保留原记录 |
| 重复投影与修改 | 重放不累计，空正文修订归零；未验收修改旧章不能改变另一章提交的总量；明确重放旧章后各投影一起更新且保持幂等 |
| 旧项目兼容 | 无新配置继续国内旧链、重复生成不写入 profile；legacy 元数据导入 123 字无正文时 state/index 同为 123 |
| 英文人名、别名与机器字段 | `Maeve O’Connell`、`Bridge-Keeper`、`M. O’Connell` 和 `bridge_sense_v2` 经提交、重复投影和索引 CLI 正确保留 |

全链路集成测试实际执行初始化 → 两次合同生成／刷新 → 上下文 → 写前 → 正文及四类事实产物 → precommit → accepted commit → state/index/summary 投影 → 重放／重试 → postcommit → 断点续跑。它使用受控原创短文本和结构化事实产物，没有调用在线生成服务来冒充模型创作质量验收。

## 独立审查修复

独立 reviewer 只读检查完整 tracked／untracked 差异并给出复现。修复前后有回归证据：未知国内辅类型模糊匹配；共享模板吞掉不同题材；旧版项目身份漏判；缺失配置的孤立 commit 降级；过期合同绕过提交；未验收旧稿影响总数；legacy 元数据 state/index 分歧；子合同刷新丢失人工覆盖字段。本轮复核又发现只有 MASTER_SETTING 的项目和中断初始化恢复边界，以及主合同 route 与 profile 快照分歧；均已添加失败测试并修复，覆盖身份不足拒绝、显式旧合同字段补齐、缺失主合同恢复、冲突写入前拒绝和重复初始化修复路由。规则包版本现在必须读取不可变归档，当前 1.1.0 也已保存逐包快照。最终只读差异复核未发现剩余可复现的 Critical、Important 或 Minor 缺陷；复核后新增的变更仅为补全显式 profile 主合同测试夹具。

保留的覆盖边界：合同刷新保护约定的人工覆盖容器，生成字段仍随生成更新。没有自动市场／语言／版本迁移工具；配置冲突应先恢复原配置。手工 StateUpdater／StateManager 数字接口保留既有“由调用方提供数值”的 API 契约，单位来自 profile。

## 规则与文学质量边界

三个国外题材包及 zh/en 两个语言包均为 **1.1.0 / draft**；原 `1.0.0` 包保留原字节归档，1.1.0 也有不可变快照。国外 draft 题材需显式试用；语言包作为表达建议加载，不给国内初始化追加授权闸门。本地 Windows 网络读取与失败项见 [来源记录](../research/2026-11-03-writing-rules-sources.md)：八个来源页面实际返回并检查标题，另有页面因 TLS 验证失败而未用作已核实依据；可达性不等于市场或文学质量证据。

[第一轮六份原创短样章观察](../research/2026-11-03-writing-rule-sample-quality.md) 与 [第二轮八章连续案例及交叉审读](../research/overseas-quality-round2/README.md) 均与自动化结果分开。第二轮修复并复核了 LitRPG 英文人物知识/报酬条件、LitRPG 中文账目区分，以及 Romantasy 供热时段/订单时限。审读为不同模型会话，不是母语编辑或读者验证；成长奇幻审查也明确披露缺少 profile 的环境限制。因此没有将题材包升级为正式支持，也没有宣称文学质量达标。

既有自然语言 `QueryRouter` 仍以中文实体正则提取图谱查询中心；直接英文人名／别名存储和查找已验证，但本次没有扩展英语自然语言图谱实体识别。嵌入／重排服务没有使用用户凭据联网压力测试。面板验证包含 API 一致性、标签源码和发行构建，没有声称浏览器端视觉验收。

使用方式见 [市场与正文语言配置指南](../guides/writing-profiles.md)。变更保留在本地功能分支工作区，未提交或推送。
