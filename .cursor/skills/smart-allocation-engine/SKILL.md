---
name: smart-allocation-engine
description: >-
  Operates the weathmanage smart allocation engine: one-click optimal rebalance,
  single-category optimize, manual tweak, product-level edits, and smart
  allocation page UX. Use when implementing or debugging 一键智能配仓,
  auto_rebalance, smart_allocation.html, or allocation results.
---

# 智能配仓引擎

## 产品定位

**在模型目标区间内，用尽量少的买卖，把客户持仓调到合理位置，并落实到具体产品。**

面向理财经理的核心能力：看得懂区间、信得过算法、留得住人工微调空间。

## 三种配仓路径

| 用户操作 | 适用场景 |
|----------|----------|
| **全账户一键 / 单类优化** | 默认路径；结构健康或需整体/单类再平衡 |
| **个性化（标志驱动）** | 投资规划 + 有业绩/风险健康标志 |
| **个性化（最优 + 分步）** | 投资规划；无标志也可分步落实产品 |
| **方案内改产品金额** | 手工配置，只校验不重算大类 |

详见 `flag-personalized-allocation`、`optimal-personalized-allocation`。

## 规划类型

| 规划类型 | 卡片维度 |
|----------|----------|
| **投资规划**（主路径） | 现金 / 固收 / 权益 / 另类 |
| **综合规划** | 四笔钱 |

同一套引擎，通过 `product_category` 分支读取不同阈值。

## 算法总览（业务语言）

```text
① 算总资产（持仓 + 追加持仓）
② 查模型 → 每大类有基准与区间
③ 大类求解 → 目标金额（区间内最小异动）
④ [可选] 产品触顶 → 冻结后重算
⑤ 拆到具体产品
⑥ 输出校验与说明
```

**核心原则：**

1. 已在区间内 → 尽量不动
2. 越界了 → 按策略拉回
3. 产品层优先在现有持仓间分配
4. 大类目标之和 = 总资产

逐步说明 → [algorithm.md](algorithm.md)

## 业务概念

| 说法 | 含义 |
|------|------|
| 追加持仓 | 待配置活钱，并入活钱大类参与求解 |
| 在区间内 | 方案占比落在模型 band 内 |
| 次优解 | 触产品限额或区间塞不下 |
| 超配/低配 | 相对基准建议减/增 |
| 类内集中 | 一只主产品承接增减 |

## API 示例

```json
POST /api/allocation/auto_rebalance
{
  "customer_id": "C20250602001",
  "mode": "smart_one_click",
  "product_category": "投资规划",
  "loss_key": "loss_6pct",
  "idle_cash": 500000
}
```

## 核心模块

| 模块 | 路径 |
|------|------|
| 引擎 | `asset_allocation/auto_rebalance_engine.py` |
| 规则注入 | `core/allocation_config_service.py` |
| 标志求解 | `asset_allocation/flag_driven_solver.py` |
| API | `api/routes.py` |
| 前端 | `smart_allocation_setup.html`, `smart_allocation.html` |

阈值从哪来 → `four-money-rules` Skill。

## 结果怎么读

- **category_summary**：现况 → 方案 → 区间 → 是否在带内
- **product_deltas**：买/卖/持有、金额、是否触限额
- **validation_notes**：向经理解读次优、触顶等原因

## 排查表

| 现象 | 常见原因 |
|------|----------|
| 0 持仓产品不在方案里 | 设计如此；需手工添加 |
| 单类优化后未满配 | 其他大类被冻结 |
| 阈值不对 | loss_key 或模型配置 |
| 个性化与一键结果混淆 | mode 不同，求解器不同 |

```bash
pytest tests/test_allocation.py -v
python demo_test.py --customer C20250602001
```

## 与其他 Skill

| Skill | 关系 |
|-------|------|
| `four-money-rules` | 阈值、模型、产品规则 |
| `flag-personalized-allocation` | 标志驱动大类 |
| `optimal-personalized-allocation` | 最优大类 + 分步落实 |

典型场景 → [scenarios.md](scenarios.md)  
算法细节 → [algorithm.md](algorithm.md)
