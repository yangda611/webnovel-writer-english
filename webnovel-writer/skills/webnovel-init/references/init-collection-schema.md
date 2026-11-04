# 初始化收集对象（内部数据模型）

> `/webnovel-init` 在 Deep 采集阶段按本结构逐项收集信息；字段齐全并过「充分性闸门」后再执行 `webnovel.py init`。本文件是字段参考，不是执行脚本。

```json
{
  "project": {
    "title": "",
    "genre": "",
    "market": "domestic",
    "body_language": "zh",
    "primary_genre": "",
    "secondary_genres": [],
    "chapter_length": 0,
    "chapter_unit": "characters",
    "pov": null,
    "tense": null,
    "allow_draft_rules": false,
    "target_words": 0,
    "target_chapters": 0,
    "one_liner": "",
    "core_conflict": "",
    "target_reader": "",
    "platform": ""
  },
  "protagonist": {
    "name": "",
    "desire": "",
    "flaw": "",
    "archetype": "",
    "structure": "单主角"
  },
  "relationship": {
    "heroine_config": "",
    "heroine_names": [],
    "heroine_role": "",
    "co_protagonists": [],
    "co_protagonist_roles": [],
    "antagonist_tiers": {},
    "antagonist_level": "",
    "antagonist_mirror": ""
  },
  "golden_finger": {
    "type": "",
    "name": "",
    "style": "",
    "visibility": "",
    "irreversible_cost": "",
    "growth_rhythm": ""
  },
  "world": {
    "scale": "",
    "factions": "",
    "power_system_type": "",
    "social_class": "",
    "resource_distribution": "",
    "currency_system": "",
    "currency_exchange": "",
    "sect_hierarchy": "",
    "cultivation_chain": "",
    "cultivation_subtiers": ""
  },
  "constraints": {
    "anti_trope": "",
    "hard_constraints": [],
    "core_selling_points": [],
    "opening_hook": ""
  }
}
```

先收集市场，再在国外分支收集中文/英文正文，再收集主类型与全部辅类型，然后进入原有问答。`project` 里的字段是收集对象；生成后以 `.story-system/WRITING_PROFILE.json` 为唯一持久配置。包版本由 registry 固定并由 helper 校验，不由模型猜测。国内默认中文；国外中文与国外英文使用同一国外题材包。国外 draft 题材试用必须显式授权；语言包保持 draft 表达建议，不对国内中文初始化额外设闸门。未知类型保留原输入逐项报错，不丢弃第三个或更多辅类型。章长为正数，单位跟随正文语言，英文目标使用 words。详见 `../../../references/writing-rules/README.md`。

## 字段与采集步骤对应

| 字段组 | 对应 Step | 说明 |
|--------|-----------|------|
| `project.market/body_language/primary_genre/secondary_genres` | Step 1.2 | 市场→国外正文语言→主类型与全部辅类型；已知选择不重问 |
| 其余 `project.*` | Step 2 | 故事核与商业定位、章长单位、可选 POV/时态/平台 |
| `protagonist.*` | Step 3 | 主角骨架（姓名/欲望/缺陷/原型/结构） |
| `relationship.*` | Step 3 | 感情线与反派分层、镜像对抗 |
| `golden_finger.*` | Step 4 | 金手指类型、风格、可见度、不可逆代价、成长节奏 |
| `world.*` | Step 5 | 世界规模、力量体系、势力、阶层、货币、境界链 |
| `constraints.*` | Step 6 | 反套路、硬约束、核心卖点、开篇钩子 |

必填项以 SKILL.md 的「充分性闸门」为准；可空字段允许留空或填「无」。
