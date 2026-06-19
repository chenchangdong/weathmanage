# SOP 投后智能体 — 配置与输出参考

## 配置文件一览

| 文件 | 职责 |
|------|------|
| `config/sop_rule_system.yaml` | indicators, rules, groups, composite_events, strategy_frameworks |
| `config/sop_product_library.yaml` | SOP 产品、管理人、category_options |
| `config/sop_agent_system.yaml` | 定时跑批、事件描述模板列、数据源声明、字数限制 |
| `config/sop_research_frameworks.yaml` | 主动权益/量化/固收+ 等分析维度与 prompt |
| `config/sop_script_templates.yaml` | 回撤/收益类话术模板 |
| `config/sop_banned_words.yaml` | replacements + strict_banned |

## content_package 结构（`run_for_event` 返回）

```json
{
  "event_id": "EVT01",
  "pipeline_version": "1.0",
  "generated_at": "2026-06-19 15:00:00",
  "agent_status": "done",
  "source": "rule_template",
  "steps": {
    "621_event_description": { "step": "6.2.1", "text": "...", "structured": {} },
    "622_product_info": { "step": "6.2.2", "static": {}, "performance": {}, "degraded": [] },
    "623_research_analysis": { "step": "6.2.3", "source": "rule_template", "analysis": {} },
    "624_client_script": { "step": "6.2.4", "text": "...", "compliance_warnings": [] }
  },
  "event_description": "...",
  "product_info": {},
  "research_analysis": {},
  "client_script": "...",
  "compliance_warnings": []
}
```

## composite_event 关键字段（6.1 产出）

| 字段 | 说明 |
|------|------|
| `event_id` | EVT01, EVT02… |
| `composite_code` | EVT_DRAWDOWN, EVT_YIELD |
| `product_code` | SOP 产品 ID（如 A108） |
| `drawdown_detail` | 规则命中描述 |
| `rule_hits` | 命中的 rule_code 列表 |
| `data_date` | 业务日期，6.2 拉数对齐此日 |
| `agent_status` | pending / running / done / failed |

## 6.2.1 事件描述模板（文本结构）

```markdown
【{data_date} 售后提醒】

- {scenario}

- 结论:
  {product_name}{drawdown_detail}

- 明细:
  产品名称 | 单日最大回撤 | ... | 触发状态
  --- | --- | ...
  {row}

命中规则：RISK_MAX_DD_5, ...
```

列定义见 `sop_agent_system.event_description.detail_columns`。

## 6.2.3 投研输出字段

| 字段 | 说明 |
|------|------|
| `framework` / `framework_label` | 映射后的分析框架 |
| `product_analysis` | 产品层归因 |
| `market_analysis` | 市场层归因 |
| `conclusion` | 现象/原因/前瞻三段 |
| `recommendation` | 持有/观察/沟通建议 |
| `structured.phenomenon/cause/outlook` | 结构化片段 |
| `report_note` | 知识库缺失时的降级说明 |

框架选择：`strategy_type` → `sop_rule_system.strategy_frameworks` → `sop_research_frameworks.frameworks[key]`。

## 6.2.4 话术与合规

- 模板键：`drawdown`（回撤事件）、`yield`（收益预警）
- 占位符：`{product_name}`, `{drawdown_summary}`, `{weekly_drawdown}`, `{max_drawdown}`, `{research_summary}`
- `SopScriptBuilder.sanitize()` 按 `sop_banned_words.yaml` 替换/屏蔽

## run-batch 请求体

```json
{
  "all_pending": true,
  "limit": 20,
  "use_llm": false,
  "event_ids": ["EVT01", "EVT02"]
}
```

响应含 `processed`, `failed`, `batch_size`, `total_pending`, `remaining_pending`, `reset_running`。

## 与 6.1 规则策略页的关系

| 能力 | 规则策略页 | 6.2 智能体 |
|------|------------|------------|
| 指标/表达式/组合事件 | ✅ 配置 | ❌ 只读消费 |
| 跑批写日志 | ✅ | ❌ 触发入口在 SOP 页/API |
| 事件描述/投研/话术 | ❌ | ✅ |
| 产品静态信息 | ❌ | ✅ SOP 产品信息库 |

规则策略「事件日志」Tab 可查看 composite_events；运行 6.2 在 SOP 投后智能体页或 API。
