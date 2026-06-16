---
name: flag-personalized-allocation
description: >-
  Operates the weathmanage flag-driven personalized allocation engine
  (FlagDrivenSolver, mode flag_personalized): health-flag scenarios,
  per-class merge rules, normalization, demo customers, and independence
  from smart_one_click. Use when implementing or debugging 个性化智能配仓, 财富健康标志配仓,
  flag_personalized, FlagDrivenSolver, or flag-driven rebalance logic.
---

# 个性化配仓（财富健康标志驱动）

## 一句话

客户**收益或风险**出了问题（有对应标志）时，按预设「处方」调整四类资产占比；**不是**简单的模型区间一键配平。

## 和「全账户一键」的关系

```text
全账户一键 smart_one_click     →  尽量在模型区间内、最小异动
个性化 flag_personalized       →  按标志主动加/减某几类（仍受 band 约束）

共用：产品怎么分到具体产品（_allocate_products_asset_type）
不共用：大类目标怎么算（FlagDrivenSolver ≠ _solve_category_targets）
```

**改个性化算法只动 `flag_driven_solver.py` + 引擎 flag 分支；禁止改 smart_one_click 求解路径。**

## 什么时候能点「个性化智能配仓」

| 条件 | 结果 |
|------|------|
| 规划类型 ≠ 投资规划 | 按钮隐藏 |
| 没有任何标志，或只有 `four_money_mismatch` | 提示「财富健康，请用全账户一键配仓」 |
| 有下面任一业绩/风险标志 | 执行 `flag_personalized` |

### 有效标志（会触发配仓）

| code | 展示名 | 什么时候出现 |
|------|--------|--------------|
| `return_below_expected` | 收益不达预期 | 实际年化 < 模型预期 − 0.5% |
| `return_above_expected` | 收益超预期 | 实际年化 > 模型预期 + 3% |
| `principal_loss_exceeded` | 本金损失超阈值 | 浮亏 > 客户可承受 loss_pct |
| `volatility_exceeded` | 波动率超预期 | 波动 > 模型预期 + 0.5% |

**不参与个性化：** `four_money_mismatch`（结构超配/低配）→ 请用一键配仓。

标志由 `WealthJourneyService.build_diagnosis()` 生成；API 服务端重新取标志，不信任前端传入。

**演示客户与操作步骤** → **[scenarios.md](scenarios.md)**（推荐 **刘女士** 复合本金亏、**孙女士** 复合波动高）。

## 四类资产与金额怎么算

| 概念 | 说明 |
|------|------|
| 四类 | 现金 / 固收 / 权益 / 另类（保障类不计入 total） |
| total | 投资类持仓 + idle_cash |
| 现金「当前」 | 现金类产品 + **idle 并入现金池**（与一键求解口径一致；见下节） |
| 每类边界 | 下限 band_lo、上限 band_hi、基准 bench |
| 现金特殊规则 | **有效下限 = max(基准, band_lo)**，不能为了凑数把现金减到基准以下 |

阈值来自 `resolve_asset_type_targets(..., loss_key?)`，与页面模型选择一致。

## 算法五步（易懂版）

完整步骤 → **[algorithm.md](algorithm.md)**

```text
① 看标志 → 确定「处方」（单场景或复合合并）
② 算意图 intent → 每类想变成多少（主动加/减谁）
③ 另类让路 → 权益需要额度时，先从另类腾挪
④ 凑满 total → 主动按顺序加/减，再被动吸收，最后残差进固收
⑤ 拆产品 → 引擎 _allocate_products_asset_type（与一键相同）
```

**直觉：** 先按「病征」开药方（intent），再在模型区间里把总金额配平（normalize），最后落到产品。

## 追加持仓口径（与一键对齐）

| 层级 | idle 怎么处理 |
|------|---------------|
| **FlagDrivenSolver 求解** | `_cash_pool`：idle **并入** cash 参与 intent / normalize（**独立算法，一键不调用**） |
| **一键 smart_one_click** | `_current_with_addon(..., "cash")` → `_solve_category_targets`（**不**调用 FlagDrivenSolver） |
| **综合规划** | `_current_with_addon(..., "spend")` |
| **category_summary 展示** | 各路径活钱类 current 均含 idle |
| **RebalanceResult** | `idle_cash` 仍单独返回 |

改 idle 口径时：**禁止**让一键走 FlagDrivenSolver；只改 `_current_with_addon` 或 Solver 内 `_cash_pool`。

## 两层逻辑：Intent 锚点 + Normalize 部署

| 层级 | 作用 |
|------|------|
| **Intent** | 基准型处方：该提/压到基准（或上/下限），**不预占 band 上沿** |
| **Normalize** | `Σintent ≠ total` 时，按 `BUY_ORDER`/`SELL_ORDER` **顺序**部署至 band 边界 |

辅助函数 `_to_bench_up` = **至少基准**：低于基准提到基准；**已高于基准不主动减**（等价 `max(bench, cur)` 在提仓方向）。

## 四个场景对照表（含主动买卖优先级）

下表 **Intent** 列是锚点；**顶满上限** 由 Normalize 在 diff>0 时按买序完成（场景 1 权益、场景 2 固收）。

### 场景 1：收益不达预期 `return_below_expected`

| 类 | Intent（锚点） | 主动卖顺序 | 主动买顺序 |
|----|----------------|------------|------------|
| 现金 | 超基准 → 降至基准 | ① | — |
| 固收 | 超上限 → 降至上限 | ② | — |
| 权益 | **至少基准**（不主动减超基准仓） | — | ① → 可加至 **上限** |
| 另类 | 带内保持（权益未到上限时不增配） | ③ | ②（仅权益触顶后） |

**主动顺序汇总：** 卖 现金→固收→另类；买 权益→另类（先加满权益上限，再另类）。

### 场景 2：收益超预期 `return_above_expected`

| 类 | Intent（锚点） | 主动卖顺序 | 主动买顺序 |
|----|----------------|------------|------------|
| 现金 | 低于基准 → 加至基准 | — | ① |
| 固收 | **至少基准**（不主动减超基准仓） | — | ② → 可加至 **上限** |
| 权益 | 超基准 → 降至基准 | ① | — |
| 另类 | 调至下限 | ② | — |

**主动顺序汇总：** 卖 权益→另类；买 **现金→固收**（先现金到基准，剩余顶固收上限）。

### 场景 3：本金损失超阈值 `principal_loss_exceeded`

| 类 | 意图（目标） | 主动卖顺序 | 主动买顺序 |
|----|--------------|------------|------------|
| 现金 | 低于基准 → 加至基准 | — | ② |
| 固收 | 调至上限 | — | ① |
| 权益 | 调至下限 | ① | — |
| 另类 | 超基准 → 降至基准 | ② | — |

**主动顺序汇总：** 卖 权益→另类；买 固收→现金。

### 场景 4：波动率超预期 `volatility_exceeded`

| 类 | 意图（目标） | 主动卖顺序 | 主动买顺序 |
|----|--------------|------------|------------|
| 现金 | 低于基准 → 加至基准 | — | ① |
| 固收 | 低于基准 → 加至基准 | — | ② |
| 权益 | 超基准 → 降至基准 | ① | — |
| 另类 | 超基准 → 降至基准 | ② | — |

**主动顺序汇总：** 卖 权益→另类；买 现金→固收。

> 凑平后仍有差额时，进入 **被动吸收**（Phase E）：买 固收→现金→另类→权益；卖 另类→权益→固收→现金（现金受基准保护，主动卖轮通常不先动现金）。

## 四个「处方」一句话（速览）

| 场景 | 核心思路 |
|------|----------|
| **收益低** | 减现金/固收（若超），Intent 锚权益≥基准，Normalize **顶满权益** 再另类 |
| **收益高** | 减权益/另类，Intent 锚固收≥基准，Normalize **先现金后固收顶满** |
| **本金亏** | 减权益/另类，**加满固收和现金**（防守） |
| **波动高** | 减权益/另类，**加现金和固收**（降波动） |

逐步算法与被动顺序 → **[algorithm.md](algorithm.md)**

## 多个标志同时亮怎么办

不是简单叠加，而是**按规则合并**（per-class 取一套意图）：

| 组合 | Intent 合并 | Normalize 买/卖顺序 |
|------|-------------|---------------------|
| 收益高 + 本金亏 | 整单「本金亏」（优先止损降风险） | 本金亏 |
| 收益低 + 本金亏 | 整单「本金亏」 | 本金亏 |
| 收益低 + 波动高 | 现金/固收/另类用「波动高」；权益折中 50% | **收益低**（保权益加仓序） |
| 本金亏 + 波动高 | 本金亏为主；权益/另类取更保守 | 本金亏 |
| 收益高 + 波动高 | 整单「波动高」 | 波动高；notes 追加「兼考虑收益偏高，权益已收到基准止盈」 |
| 三个及以上 | 按主导场景 intent | 主导场景：`本金亏 > 波动高 > 收益高 > 收益低` |

## 硬约束（不能破）

1. 每类最终目标在 `[floor, 上限]` 内  
2. 现金不低于基准  
3. 权益未到位前，另类不为权益「抢额度」（另类让路）  
4. `Σ 大类目标 ≈ total`；做不到 → `validation_notes` 次优解  

## 模块与 API

| 模块 | 路径 |
|------|------|
| 求解器 | `asset_allocation/flag_driven_solver.py` |
| 引擎接入 | `auto_rebalance_engine._rebalance_investment_planning` → `mode == "flag_personalized"` |
| 前端 | `#btnPersonalizedOptimize` |
| 测试 | `tests/test_flag_driven.py` |

```json
POST /api/allocation/auto_rebalance
{ "customer_id": "...", "mode": "flag_personalized", "product_category": "投资规划", "loss_key": "loss_6pct" }
```

## 改什么去哪个文件

| 要改 | 文件 | 不要改 |
|------|------|--------|
| 单场景每类规则 | `_scenario_intents` | `_solve_category_targets` |
| 多标志合并 | `_merged_intents` | smart_one_click 分支 |
| 凑平/让路 | `_normalize`, `_alternative_yields_equity` | four_money_rule solver |
| 权益折中系数 | `EQUITY_BLEND_RATIO` | — |
| 产品 spill | 一般共用产品层；flag 专用 freeze 才扩 flag 分支 | 一键 freeze |

## 排查

| 现象 | 查什么 |
|------|--------|
| 健康客户仍能点？ | 诊断 flags 是否只有 four_money_mismatch |
| 与一键结果一样？ | 确认 mode 是 flag_personalized |
| 现金低于基准 | `_bounds` floor、Phase D/E 卖出顺序 |
| 追加持仓未进活钱类 | `_current_with_addon` / `_cash_pool`；见 algorithm 口径节 |

```bash
pytest tests/test_flag_driven.py -v
pytest tests/test_allocation.py -k investment -v
```

## 验证清单

```
- [ ] 仅投资规划可触发
- [ ] 无有效标志 → 拒绝 + 正确文案
- [ ] smart_one_click 回归不变
- [ ] notes 含「个性化配仓依据：…」
- [ ] Σ 大类目标 ≈ total；现金 ≥ 基准
- [ ] pytest tests/test_flag_driven.py 通过
```

- 逐步算法：[algorithm.md](algorithm.md)  
- 产品层与字段解读：`../smart-allocation-engine/SKILL.md`  
- 模型阈值：`../four-money-rules/SKILL.md`  
- **典型演示场景**：[scenarios.md](scenarios.md)
