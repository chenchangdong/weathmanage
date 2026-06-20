---
name: optimal-personalized-allocation
description: >-
  Operates optimal-prescription allocation (optimal_personalized): one-click
  category targets + hold-only product layer and prescription UI. Use when
  debugging 个性化智能配仓（新）, optimal_personalized, or comparing with flag_personalized.
---

# 个性化配仓（最优 + 分步落实）

## 产品定位

**大类用全账户最优算法，产品由理财经理分步落实——适合配置健康、但仍希望可控填产品的场景。**

与「标志驱动个性化」共用同一套配置页与方案落实 UI，但**不要求**健康标志，大类目标与全账户一键一致。

## 三种配仓对照

| 方式 | 大类算法 | 产品落实 | 前置条件 |
|------|----------|----------|----------|
| 全账户一键 | 最优区间求解 | 一次配满 | 投资/综合规划 |
| 个性化（标志） | 标志处方 | 分步落实 | 投资规划 + 有标志 |
| **个性化（新）** | **同全账户一键** | **分步落实** | **仅投资规划** |

## 什么时候可用

| 条件 | 结果 |
|------|------|
| 非投资规划 | 按钮隐藏 |
| 投资规划 | 可见；**无标志也可用** |
| 配置健康（无标志） | 本模式可用；旧版标志个性化会拒绝 |

## 端到端流程

```text
配置页（客户 + 模型 + 追加持仓）
  → 资产检视
  → 点击「个性化智能配仓（新）」
  → 引擎算大类目标（product 层先全部 hold）
  → 展示大类处方卡片
  → 逐类「一键自动调仓」填产品
  → 可手工微调
```

逐步算法 → [algorithm.md](algorithm.md)  
演示 → [scenarios.md](scenarios.md)

## 引擎要点

- 大类：` _solve_category_targets`（与全账户一键相同）
- 产品：首次全部 hold，等经理逐类落实
- **不调用**标志求解器 `FlagDrivenSolver`

## 前端

| 模块 | 说明 |
|------|------|
| `#btnOptimalPersonalized` | 入口按钮 |
| `PRESCRIPTION_MODES` | 与标志个性化共用处方 UI |
| `flag_category_suggest` | 逐类产品建议 API |

两种个性化模式的处方缓存互不混用。

## API

```json
POST /api/allocation/auto_rebalance
{
  "mode": "optimal_personalized",
  "product_category": "投资规划"
}
```

不要求 diagnosis flags（与标志个性化不同）。

## 排查

| 现象 | 查什么 |
|------|--------|
| 与一键大类不一致 | solver 入参应相同 |
| 首次就有产品买卖 | mode 误为 smart_one_click |
| 按钮不可见 | 是否投资规划 |

```bash
pytest tests/test_flag_driven.py::TestOptimalPersonalizedRebalance -v
```

## 与其他 Skill

| Skill | 关系 |
|-------|------|
| `smart-allocation-engine` | 大类求解算法 |
| `flag-personalized-allocation` | 标志驱动姊妹模式 |
| `four-money-rules` | 模型阈值 |

- [algorithm.md](algorithm.md)
- [scenarios.md](scenarios.md)
