---
name: flag-personalized-allocation
description: >-
  Operates flag-driven personalized allocation (FlagDrivenSolver, mode
  flag_personalized): health-flag scenarios, per-class rules, demo customers.
  Use when implementing or debugging 个性化智能配仓, 财富健康标志配仓, or flag_personalized.
---

# 个性化配仓（健康标志驱动）

## 产品定位

**客户出现收益或风险异常时，按「处方」主动调整大类结构——不是简单的区间一键配平。**

适合：李先生（回撤预警）、刘女士（本金浮亏）、孙女士（波动超预期）等需**因症施策**的场景。

## 与一键配仓的关系

| 方式 | 大类怎么算 | 产品怎么落实 |
|------|------------|--------------|
| 全账户一键 | 模型区间内最小异动 | 一次配满 |
| **个性化（标志）** | **按健康标志开处方** | 分步落实 |
| 个性化（最优+分步） | 同全账户一键算法 | 分步落实 |

**共用**产品层分配逻辑；**不共用**大类求解算法。

## 什么时候可用

| 条件 | 结果 |
|------|------|
| 非投资规划 | 不可用 |
| 无标志，或仅「四笔钱结构问题」 | 提示用全账户一键 |
| 有业绩/风险类标志 | 执行个性化配仓 |

### 有效标志

| 展示名 | 典型含义 |
|--------|----------|
| 收益不达预期 | 实际收益低于模型预期 |
| 收益超预期 | 实际收益明显高于预期 |
| 本金损失超阈值 | 浮亏超过可承受范围 |
| 波动率超预期 | 波动高于模型预期 |

「四笔钱配置不合理」→ 请用全账户一键，不走本模式。

标志由资产诊断生成；API 服务端重新校验，不信任前端传入。

演示客户 → [scenarios.md](scenarios.md)（推荐刘女士、孙女士）

## 算法直觉（五步）

```text
① 看标志 → 确定处方（单场景或复合合并）
② 算意图 → 每类想变成多少
③ 另类让路 → 权益需要额度时先从另类腾挪
④ 凑满总资产 → 主动加/减 + 被动吸收
⑤ 拆产品 → 与一键共用产品层
```

详细步骤 → [algorithm.md](algorithm.md)

## 四个典型处方（速览）

| 场景 | 核心思路 |
|------|----------|
| **收益偏低** | 减现金/固收（若超），加仓权益 |
| **收益偏高** | 减权益/另类，加仓现金/固收 |
| **本金亏损** | 减权益/另类，加满固收和现金 |
| **波动过高** | 减权益/另类，加现金和固收 |

多标志同时出现时按规则合并，不是简单叠加。

## 硬约束

1. 每类最终在模型区间内
2. 现金不低于基准
3. 权益未到位前，另类不为权益抢额度
4. 大类目标之和 ≈ 总资产

## 模块与 API

| 模块 | 路径 |
|------|------|
| 求解器 | `asset_allocation/flag_driven_solver.py` |
| 引擎接入 | `auto_rebalance_engine` flag 分支 |
| 前端 | `#btnPersonalizedOptimize` |

```json
POST /api/allocation/auto_rebalance
{ "mode": "flag_personalized", "product_category": "投资规划" }
```

## 排查

| 现象 | 查什么 |
|------|--------|
| 健康客户仍能点？ | 是否只有结构类标志 |
| 与一键结果一样？ | mode 是否为 flag_personalized |
| 现金低于基准 | 求解器 bounds 与凑平顺序 |

```bash
pytest tests/test_flag_driven.py -v
```

## 与其他 Skill

| Skill | 关系 |
|-------|------|
| `smart-allocation-engine` | 产品层、结果字段 |
| `four-money-rules` | 模型阈值 |
| `optimal-personalized-allocation` | 姊妹模式（无标志也可分步） |

- 算法：[algorithm.md](algorithm.md)
- 场景：[scenarios.md](scenarios.md)
