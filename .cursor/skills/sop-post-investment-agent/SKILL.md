---
name: sop-post-investment-agent
description: >-
  Operates weathmanage SOP post-investment agent: 6.1 rule batch (event detection),
  6.2 content pipeline (event description, product info, research, client script),
  SOP product library, and ops admin pages. Use when implementing or debugging
  SOP投后智能体, sop_agent, run-batch, SopAgentPipeline, sop_events.json,
  rule strategy, or separating SOP products from allocation product_constraint.
---

# SOP 投后智能体

## 一句话

**6.1 判是否报警** → **6.2 报警后说什么**（事件描述 + 投研 + 对客话术）。不含飞书推送（6.2.5）与策略下发（6.3）。

```text
规则跑批 → composite_event (agent_status=pending)
         → SopAgentPipeline (621→622→623→624)
         → content_package 写入 agent_outputs
```

## 与资配 / 投后陪伴 / sop-SKILL.md 的边界

| 域 | 配置/模块 | 用途 |
|----|-----------|------|
| **资配底层产品** | `config/product_constraint.yaml` | 调仓引擎 P000–P011，**SOP 不用** |
| **SOP 产品库** | `config/sop_product_library.yaml` | 6.1 扫品 + 6.2 静态画像（A108 等） |
| **6.1 规则** | `config/sop_rule_system.yaml` + 规则策略页 | 指标/规则/组合事件 |
| **6.2 智能体** | `config/sop_agent_system.yaml` 等 | 描述模板、框架、话术、调度 |
| **运行时事件** | `data/sop_events.json` | 跑批日志 + 组合事件 + 智能体输出（**gitignore**） |

- 已删除 **投后陪伴**（`aftercare_*`），SOP 独立实现。
- 根目录 `sop-SKILL.md` 是 OpenClaw/Excel 外链技能说明，**不是**本仓库运行时；本 skill 描述 **Web + API 实现**。

## 6.2 四步管道

| 步骤 | 配置/代码 | 输出 |
|------|-----------|------|
| **6.2.1** 事件描述 | `sop_agent_system.yaml` → `event_description`；`SopAgentPipeline.step_621_*` | Skill Step 3 风格 Markdown |
| **6.2.2** 产品信息 | `SopProductInfoService`；降级：`sop_product_library` + `mock_product_metrics` | `static` + `performance` + `degraded[]` |
| **6.2.3** 投研分析 | `sop_research_frameworks.yaml` + `sop_rule_system.strategy_frameworks`；可选 LLM | 300–350 字结构化结论 |
| **6.2.4** 对客话术 | `sop_script_templates.yaml` + `sop_banned_words.yaml` | 200–250 字 + 合规替换 |

编排入口：`core/sop_agent_pipeline.py` → `SopAgentService.run_for_event()`。

**LLM 策略：**

- 单条 `POST /api/sop/agent/run`：配置 Key 时 6.2.3 可 LLM 增强（`source: llm`）。
- 批量 `POST /api/sop/agent/run-batch`：默认 `use_llm: false`，规则模板快速模式，**每批最多 20 条**。

## 核心模块

| 模块 | 路径 |
|------|------|
| 6.1 规则引擎 | `core/sop_rule_engine.py` |
| 事件持久化 | `core/sop_event_store.py`（原子写入 + 文件锁） |
| 6.2 管道 | `core/sop_agent_pipeline.py` |
| 6.2 服务 | `core/sop_agent_service.py` |
| SOP 产品库 CRUD | `core/sop_product_library_service.py` |
| 定时跑批 | `core/sop_batch_scheduler.py`（默认 21:00） |
| 话术/禁用词 | `core/sop_script_builder.py` |

## 前端入口

| 页面 | 路径 |
|------|------|
| SOP 投后智能体 | `frontend/sop_agent.html` |
| 规则策略 | `frontend/admin/rule_strategy.html` |
| SOP 产品信息库 | `frontend/admin/sop_product_library.html` |

演示：跑批触发 → 查询事件 / 批量运行 6.2 → 单条「运行智能体」→ **三块展示**（事件描述 / 投研 / 话术）。

## API 速查

```text
GET  /api/sop/system                    # 6.1 规则配置
POST /api/sop/events/run-batch          # 6.1 跑批
GET  /api/sop/events                    # 组合事件列表
POST /api/sop/agent/query               # 自然语言查事件
POST /api/sop/agent/run                 # 单条 6.2
POST /api/sop/agent/run-batch           # 批量 6.2 { all_pending, limit, use_llm }
GET  /api/sop/agent/output?event_id=    # 读取已生成内容包
GET  /api/sop/agent/config              # 6.2 配置
GET  /api/sop/agent/schedule/status     # 定时任务状态
POST /api/sop/events/scheduled-batch    # 手动触发 21:00 流程

/api/sop/info-products/  /managers/     # SOP 产品库（独立 router）
```

## 配置决策树

```text
改阈值/表达式/组合事件？     → sop_rule_system.yaml + 规则策略页（不动 6.2）
改 SOP 产品静态信息？         → sop_product_library.yaml + SOP产品信息库页
改事件描述模板列？            → sop_agent_system.event_description
改投研框架维度？              → sop_research_frameworks.yaml
改策略类型→框架映射？         → sop_rule_system.strategy_frameworks
改话术模板/禁用词？           → sop_script_templates / sop_banned_words
改定时跑批时间？              → sop_agent_system.batch_schedule
```

改 YAML 后：`reload_all_configs()` 或重启服务；`save_sop_*` 写入函数会自动 reload。

## 数据降级（当前无评价库/知识库）

| 数据 | 现状 | 将来接入点 |
|------|------|------------|
| 静态产品 | `SopProductLibraryService` | 替换 `data_sources.product_static` |
| 业绩指标 | `mock_product_metrics()` | 评价 API → `product_performance` |
| 研报 | 无，`report_note` 标注降级 | 知识库 → `product_reports` |

**禁止**用 `product_constraint.yaml` 充当 SOP 产品源。

## agent_status 状态机

```text
pending → running → done | failed
```

- 跑批新建事件：`agent_status: pending`
- 中断遗留 `running`：批量前 `reset_stale_running()` 重置为 pending
- 完成后写入 `data/sop_events.json` 的 `agent_outputs[event_id]`

清空事件库：重置 `data/sop_events.json` 为默认空结构后重新跑批。

## 开发与调试

```bash
# 测试
.venv/bin/python -m pytest tests/test_sop.py tests/test_sop_agent_pipeline.py tests/test_sop_product_library.py -q

# 本地 API 冒烟
curl -X POST localhost:8000/api/sop/events/run-batch -H 'Content-Type: application/json' -d '{}'
curl -X POST localhost:8000/api/sop/agent/run-batch -H 'Content-Type: application/json' \
  -d '{"all_pending":true,"limit":5}'
```

**常见坑：**

1. 批量 6.2「无反应」→ 事件过多 + 单条 LLM 慢；用 `limit` + `use_llm:false`，前端需即时 loading。
2. `sop_events.json` 膨胀 → 运行时数据，勿提交 git；可定期清空。
3. 并发写 JSON 损坏 → 已用 tmp 原子替换；勿多进程同时写同一文件。
4. 6.1 产品 ID 与资配 P 码混用 → 跑批扫描 `SopProductLibraryService.get_product_map()`。

## 改动检查清单

- [ ] SOP 产品改动只动 `sop_product_library.yaml`，未改 `product_constraint`
- [ ] 6.2 管道四步输出字段与前端三块展示一致
- [ ] 批量 API 默认 limit ≤ 20、use_llm=false
- [ ] 新增配置已接入 `config_loader` / `reload_all_configs`
- [ ] 相关 pytest 通过

## 延伸阅读

- 配置与输出字段详情 → [reference.md](reference.md)
- 外链 Excel/飞书全流程 → 仓库根目录 `sop-SKILL.md`（非本实现）
