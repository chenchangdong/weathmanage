---
name: sop-post-investment-agent
description: >-
  Operates wealthmanagement post-investment SOP: rule batch, content generation,
  Feishu push, scheduled tasks, and ops admin. Use when implementing or
  debugging 投后SOP管理台, sop_agent, run-batch, SopAgentPipeline, sop_events.json,
  rule strategy, or SOP product library.
---

# 投后 SOP 管理

## 产品定位

**把投后预警变成可执行、可触达的售后动作。**

| 环节 | 业务价值 |
|------|----------|
| **事件识别** | 日终扫描产品，自动发现回撤、收益等异常 |
| **内容生成** | 产出事件说明、投研分析、对客话术等完整材料 |
| **经理触达** | 按持有关系，飞书一对一推送给客户经理 |
| **定时运营** | 支持每晚自动跑批，也保留手动触发 |

```text
规则跑批 → 组合事件（待处理）
         → 内容管道（描述 / 投研 / 话术）
         → 可选飞书推送
```

## 与资配、产品库的边界

| 域 | 配置/模块 | 用途 |
|----|-----------|------|
| **资配底层产品** | `product_constraint.yaml` | 调仓引擎专用，**投后 SOP 不使用** |
| **投后产品库** | `product_library.yaml` / SOP 产品页 | 跑批扫描 + 产品静态画像 |
| **预警规则** | `sop_rule_system.yaml` + 规则策略页 | 指标、规则、组合事件 |
| **智能体与调度** | `sop_agent_system.yaml` | 描述模板、话术、定时任务、推送 |
| **运行时事件** | `data/sop_events.json` | 跑批日志 + 事件 + 生成内容（**gitignore**） |

- 已删除旧版「投后陪伴」模块，SOP 为独立实现。
- 根目录 `sop-SKILL.md` 为外链/Excel 说明，**非**本仓库 Web 运行时。

## 内容生成管道（四步）

| 步骤 | 产出 | 说明 |
|------|------|------|
| **事件描述** | Markdown 结构化说明 | 按模板列展示产品、回撤、触发状态等 |
| **产品信息** | 静态 + 业绩 | 产品库为主，业绩可 mock 降级 |
| **投研分析** | 300–350 字结论 | 按策略框架；可选大模型增强 |
| **对客话术** | 200–250 字 | 模板 + 禁用词合规替换 |

编排入口：`core/sop_agent_pipeline.py` → `SopAgentService.run_for_event()`

**生成策略：**

- 单条生成：配置大模型 Key 时可 LLM 增强投研
- 批量生成：默认规则模板快速模式，**每批最多 20 条**

## 定时任务与推送

| 能力 | 入口 |
|------|------|
| 定时跑批 | `运营管理 → 批量任务` 或 `sop_agent_system.batch_schedule` |
| 链式自动化 | 可配置：跑批 → 智能生成 → 飞书推送 |
| 飞书账号 | `advisor_directory.yaml` 配手机/邮箱/工号，自动解析 open_id |
| 手动触发 | 投后SOP管理台 + `POST /api/sop/events/scheduled-batch` |

## 核心模块

| 模块 | 路径 |
|------|------|
| 规则引擎 | `core/sop_rule_engine.py` |
| 事件持久化 | `core/sop_event_store.py` |
| 内容管道 | `core/sop_agent_pipeline.py` |
| 智能体服务 | `core/sop_agent_service.py` |
| 飞书推送 | `core/sop_push_service.py` |
| 定时调度 | `core/sop_batch_scheduler.py` |
| 产品库 | `core/sop_product_library_service.py` |

## 前端入口

| 页面 | 路径 |
|------|------|
| 投后SOP管理台 | `frontend/sop_agent.html` |
| 批量任务 | `frontend/admin/sop_batch_trigger.html` |
| 规则策略 | `frontend/admin/rule_strategy.html` |
| 产品信息库 | `frontend/admin/sop_product_library.html` |

## API 速查

```text
POST /api/sop/events/run-batch          # 规则跑批
GET  /api/sop/events                    # 事件列表
POST /api/sop/agent/run                 # 单条内容生成
POST /api/sop/agent/run-batch           # 批量生成
POST /api/sop/agent/push                # 飞书推送
PUT  /api/sop/agent/schedule/config     # 定时任务配置
POST /api/sop/events/scheduled-batch    # 手动触发定时流程
GET  /api/sop/agent/schedule/status     # 调度状态
```

## 配置决策

| 要改什么 | 改哪里 |
|----------|--------|
| 预警阈值 / 规则 | `sop_rule_system.yaml` + 规则策略页 |
| 投后产品信息 | 产品信息库页 / `product_library.yaml` |
| 事件描述模板 | `sop_agent_system.event_description` |
| 投研框架 | `sop_research_frameworks.yaml` |
| 话术 / 禁用词 | `sop_script_templates` / `sop_banned_words` |
| 定时跑批 / 自动推送 | 批量任务页 / `batch_schedule` |

## 事件状态

```text
待生成 → 生成中 → 已完成 | 失败
推送：待推送 → 已推送 / 部分推送 / 失败
```

## 开发与调试

```bash
pytest tests/test_sop.py tests/test_sop_agent_pipeline.py tests/test_sop_feishu_push.py -q

curl -X POST localhost:8000/api/sop/events/run-batch -H 'Content-Type: application/json' -d '{}'
curl -X PUT localhost:8000/api/sop/agent/schedule/config -H 'Content-Type: application/json' \
  -d '{"enabled":true,"hour":20,"minute":0,"run_agent_after_batch":true,"push_feishu_after_agent":false}'
```

**常见坑：**

1. 批量生成慢 → 用 `limit` + 关闭 LLM
2. `sop_events.json` 膨胀 → 运行时数据，勿提交 git
3. 投后产品 ID 与资配 P 码混用 → 跑批扫描 SOP 产品库

## 改动检查清单

- [ ] 投后产品改动不动 `product_constraint`
- [ ] 管道输出与前端三块展示一致
- [ ] 批量 API 默认 limit ≤ 20
- [ ] 定时任务配置与批量任务页一致
- [ ] 相关 pytest 通过

## 延伸阅读

- 配置与字段详情 → [reference.md](reference.md)
