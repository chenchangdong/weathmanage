---
name: smart-allocation-engine
description: >-
  Operates the weathmanage smart allocation engine: one-click optimal rebalance,
  single-category optimize, manual tweak, and product-level edits. Explains
  in-band vs suboptimal results, over/under allocation, and rebalance output
  fields. Use when implementing or debugging 一键智能最优配置, 单类智能优化,
  auto_rebalance, allocation results, product_deltas, or 次优解.
---

# 智能配仓引擎

## 业务能力定义

为理财经理提供**一键智能最优配置**：在客户风险对应模型区间内，以最小资金异动原则，将大类目标分配到底层产品，输出可执行的调仓方案。支持全账户、单类优化、人工微调、产品级二次调仓。

## 业务概念词典

| 术语 | 含义 | 看哪个字段 |
|------|------|------------|
| 在区间内 | 目标/当前占比落在模型 band 内 | `category_summary[].in_band` |
| 次优解 | 方案目标仍可能越界或无法完全达标 | `validation_notes` |
| 超配/低配 | 相对模型基准建议减/增 | `adjust_amount` 正/负 |
| 最小异动 | 已在区间内的大类保持现仓 | solver `minimize_cash_movement` |
| 类内集中 | 一只主产品承接大类增减 | solver `consolidate_category_rebalance` |

**注意**：`in_band`（是否落在区间）与 `adjust_amount`（相对基准方向）是不同维度。

## 核心模块

| 模块 | 路径 |
|------|------|
| 引擎 | `asset_allocation/auto_rebalance_engine.py` |
| 规则注入 | `core/allocation_config_service.py` |
| API | `POST /api/allocation/auto_rebalance` |
| 手工调仓 | `POST /api/allocation/manual_adjust` |
| 产品候选 | `GET /api/products/candidates` |
| 前端 | `frontend/smart_allocation.html` + `js/plan_editor.js` |

规则来源见 `four-money-rules` Skill，本 Skill 聚焦**怎么算、怎么用、怎么读**。

## 配仓模式（mode）

| mode | 业务场景 | 入口 |
|------|----------|------|
| `smart_one_click` | 全账户或单类一键最优 | 页面「全账户一键…」「一键单类智能优化」 |
| `manual_tweak` | 理财经理锁定部分大类后重算 | 人工微调弹窗 |
| `manual_product_edit` | 产品级目标金额手调 | 方案编辑器 |

### 全账户一键最优

```json
POST /api/allocation/auto_rebalance
{
  "customer_id": "C20250602001",
  "mode": "smart_one_click"
}
```

求解步骤：
1. `resolve_profile_targets` 获取各大类 `target` + `band`
2. `_solve_category_targets`：在 band 内尽量保持现仓；越界按 `fallback_strategy` 回退
3. `_allocate_products`：类内按优先级 consolidate + spill
4. 输出 `category_summary`、`product_deltas`、`validation_notes`

### 单类智能优化

请求增加 `"target_category": "grow"`（或其他大类 code）。

业务规则：
- **其余大类冻结**在当前持仓，不归一化凑满总资产
- **超配**：减至模型 **benchmark**（非 band 中点）
- **低配**：仍用 `fallback_strategy`（默认 `band_midpoint`）
- 未纳入配置的闲置资金会写入 `validation_notes`

### 人工微调 / 产品编辑

- `locked_categories`：冻结大类
- `manual_overrides`：指定大类目标金额
- 手工添加 0 持仓产品：仅 `manual_product_edit` 路径；智能一键**不参与** 0 持仓产品

## 产品分配规则

1. **智能配仓仅在有持仓的产品间**分配与 spill（`_held_products`）
2. `consolidate_category_rebalance=true`：优先级最高产品承接，触 `min_amount`/`max_amount` 时 spill
3. `liquidate_below_min=true`：减仓可至 0，`limit_hit=min`
4. 产品目标加总 = 大类目标（测试强制不变式）

## 结果解读（给理财经理）

### category_summary 关键字段

| 字段 | 说明 |
|------|------|
| `current_ratio` | 检视：当前占比 |
| `final_ratio` | 方案：目标占比 |
| `band` | 模型区间 [下, 上] |
| `in_band` | 方案是否在区间内 |
| `adjust_amount` | 相对基准的调整金额（正=建议减，负=建议增） |

### product_deltas

| 字段 | 说明 |
|------|------|
| `action` | `buy` / `sell` / `hold` |
| `delta_amount` | 调整金额 |
| `limit_hit` | 触 `min` 或 `max` |
| `limit_side` | 触限方向 |

### validation_notes

次优解、单类缺口、限额冲突等说明，演示时应主动解读。

## 标准业务路径（演示）

1. 选择客户（如张女士 `C20250602001`）
2. `GET /api/asset/overview` 查看检视与健康度
3. `POST /api/allocation/auto_rebalance` 全账户一键
4. 页面展示方案 → 「生成配置解读」
5. AI 对话可追问（依赖 `overviewData` + `planData`）

```bash
python demo_test.py --customer C20250602001
python demo_test.py --all
```

## 常见业务问题排查

| 现象 | 先查 | 可能原因 |
|------|------|----------|
| 0 持仓产品未出现在方案 | `product_deltas` | 智能配仓排除 0 持仓；需手工添加 |
| 单类优化后总资产不满配 | `validation_notes` | 其他大类冻结，设计如此 |
| 超配未减到预期 | resolve + solver | 单类超配减至 benchmark；全账户看 fallback |
| 产品触下限无法继续减 | `limit_hit` | `min_amount` 或 `liquidate_below_min` |
| 阈值本身不对 | resolve API | 改配置见 `four-money-rules` |

```bash
# 场景测试
pytest tests/test_allocation.py -v

# 指定场景
pytest tests/test_allocation.py -k "single_category or consolidate" -v
```

关键测试客户：`C20250602001`（平衡）、`C20250602002`（保守边界）。

## 与周边能力边界

| 能力 | 关系 |
|------|------|
| 四笔钱规则 | 提供 targets/band；改规则不改引擎 |
| 资产检视 | 配仓前的 `current_ratio` 输入 |
| ExplainAgent | 消费 rebalance 结果生成解读（规则版，非 LLM） |
| AI 顾问对话 | 可传入 plan 做 grounding 追问 |

## 验证检查清单

```
- [ ] resolve 阈值与客户风险一致
- [ ] category_summary 各大类 in_band 符合预期
- [ ] product_deltas 仅含应调仓产品
- [ ] 产品目标加总 = 大类目标
- [ ] validation_notes 已向经理解读（有次优时）
- [ ] pytest tests/test_allocation.py 通过
```

详细场景见 [scenarios.md](scenarios.md)。
