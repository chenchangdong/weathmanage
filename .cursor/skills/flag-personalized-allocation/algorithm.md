# 个性化配仓算法说明

实现：`asset_allocation/flag_driven_solver.py`  
主 Skill：[SKILL.md](SKILL.md)

---

## 先建立直觉

想象客户总资产是一个**固定大小的饼**（total），要切成四块：现金、固收、权益、另类。

1. **诊断**告诉你是哪种「病」（收益低、收益高等）
2. **处方**说每块饼想变大还是变小（intent）
3. **归一化**在模型允许范围内，把四块重新切，保证加起来还是整个饼
4. **产品层**再把每块饼分到具体产品

---

## 符号（读后面步骤用）

| 符号 | 含义 |
|------|------|
| total | 投资类持仓 + idle_cash |
| cur[c] | 当前该类金额；**cash 含 idle** |
| bench | 模型基准金额 = target × total |
| lo / hi | 区间下/上限金额 |
| floor | 有效下限；现金 = max(bench, lo)，其他 = lo |
| intent | 处方算出的「意图金额」 |
| tgt | 归一化后最终大类目标 |
| ε | 0.01 元，判断「算平了没」 |

---

## 整体流程

```text
标志过滤 → 合并处方(intent) → 另类让路 → 初始化 tgt
    → [差额?] 主动凑平 → 被动吸收 → 残差 spill → 返回 tgt
```

---

## Step 1：过滤标志

```text
有效标志 = flag_codes 里属于 {收益低, 收益高, 本金亏, 波动高} 的
若为空 → 报错「财富健康，请用全账户一键配仓」
four_money_mismatch 永远不参与
```

同时：`cur = 当前各类 + idle 并入 cash`，`bounds = 每类 bench/lo/hi/floor`。

---

## Step 2：单场景处方 `_scenario_intents`

**Intent 锚点规则（场景 1 / 2）：**

- 场景 1 权益：`to_bench_up`（至少基准，不主动减超基准仓）；Normalize `BUY [权益, 另类]` 顶至上限。
- 场景 2 固收：`to_bench_up`（至少基准，不主动减超基准仓）；Normalize `BUY [现金, 固收]` 顶至上限。

每个场景对四类分别指定「意图金额」。辅助动作含义：

| 动作 | 白话 |
|------|------|
| 降至基准 | 现在比基准多 → 收到基准；否则不动 |
| 加至基准 | 现在比基准少 → 补到基准；否则不动 |
| 降至上限 | 现在超上限 → 收到上限；否则不动 |
| 调至上限/下限 | 直接设到上限或下限 |
| 带内保持 | 在 [floor, hi] 内保持现仓 |

### 场景对照表（含主动买卖优先级）

**说明：** 「主动卖 / 主动买」为 Phase D 凑平时的执行顺序（`SELL_ORDER` / `BUY_ORDER`）。  
`①` 最先、`②` 次之、`③` 再次；`—` 表示该方向不主动排队（仍可能被动吸收）。

#### 场景 1：收益不达预期 `return_below_expected`

| 类 | Intent（锚点） | 主动卖顺序 | 主动买顺序 |
|----|----------------|------------|------------|
| 现金 | 超基准 → 降至基准 | ① | — |
| 固收 | 超上限 → 降至上限 | ② | — |
| 权益 | **至少基准** | — | ①（Normalize 可加至 hi） |
| 另类 | 带内保持 | ③ | ②（权益触顶后） |

#### 场景 2：收益超预期 `return_above_expected`

| 类 | Intent（锚点） | 主动卖顺序 | 主动买顺序 |
|----|----------------|------------|------------|
| 现金 | 低于基准 → 加至基准 | — | ① |
| 固收 | **至少基准** | — | ②（Normalize 可加至 hi） |
| 权益 | 超基准 → 降至基准 | ① | — |
| 另类 | 调至下限 | ② | — |

#### 场景 3：本金损失超阈值 `principal_loss_exceeded`

| 类 | 意图 | 主动卖顺序 | 主动买顺序 |
|----|------|------------|------------|
| 现金 | 低于基准 → 加至基准 | — | ② |
| 固收 | 调至上限 | — | ① |
| 权益 | 调至下限 | ① | — |
| 另类 | 超基准 → 降至基准 | ② | — |

主动顺序：**卖** 权益 → 另类；**买** 固收 → 现金。

#### 场景 4：波动率超预期 `volatility_exceeded`

| 类 | 意图 | 主动卖顺序 | 主动买顺序 |
|----|------|------------|------------|
| 现金 | 低于基准 → 加至基准 | — | ① |
| 固收 | 低于基准 → 加至基准 | — | ② |
| 权益 | 超基准 → 降至基准 | ① | — |
| 另类 | 超基准 → 降至基准 | ② | — |

主动顺序：**卖** 权益 → 另类；**买** 现金 → 固收。

---

## Step 3：多标志合并 `_merged_intents`

返回 `(intent, passive, normalize_key)`：`normalize_key` 决定 Phase D 的 `BUY_ORDER`/`SELL_ORDER`（可与主导优先级不同，如收益低+波动高仍用收益低买序）。

```text
收益高 + 本金亏     → Intent「本金亏」；normalize_key = 本金亏
收益低 + 本金亏     → Intent「本金亏」；normalize_key = 本金亏
收益低 + 波动高     → 权益折中 50%；normalize_key = 收益低
本金亏 + 波动高     → min(本金亏,波动)  on 权益/另类；normalize_key = 本金亏
收益高 + 波动高     → Intent「波动高」；normalize_key = 波动高
                    → notes：「兼考虑收益偏高，权益已收到基准止盈」
仅一个标志         → 该场景
三个及以上         → 主导 intent + normalize_key（见下）
```

主导优先级（三标志及以上）：**本金亏 > 波动高 > 收益高 > 收益低**

---

## Step 4：另类让路 `_alternative_yields_equity`

**规则：** 权益还没配够 intent 之前，另类不能占增配额度。

```text
权益缺口 = max(0, intent[权益] − cur[权益])
若缺口 > 0：
  从另类可释放额度中挪给权益（不超过另类 floor 以上部分）
若权益仍未到上限：
  另类 intent 不超过「带内保持」水平
```

---

## Step 5：归一化 `_normalize`（凑满 total）

初始化 `tgt = round(intent)`，算 `diff = total − Σtgt`。

### Phase D — 主动凑平（按主导场景的买卖顺序）

**需要加钱（diff > 0）** — 按 BUY_ORDER 依次加，每类不超过 hi：

```text
收益低：先权益 → 再另类
收益高：先现金 → 再固收
本金亏：先固收 → 再现金
波动高：先现金 → 再固收
```

**需要减钱（diff < 0）** — 按 SELL_ORDER 依次减，每类不低于 floor：

```text
收益低：现金 → 固收 → 另类
收益高/本金亏/波动：权益 → 另类
（现金卖出受基准保护，排最后被动处理）
```

### Phase E — 被动吸收

主动后仍有差额：用固定顺序在 band 内继续吸收。

```text
被动买入顺序：固收 → 现金 → 另类 → 权益
被动卖出顺序：另类 → 权益 → 固收 → 现金
```

本轮「主动不动」的类可在 notes 标为被动吸收。

### Phase F — 残差 spill

仍不平 → 默认把剩余差额尽量放进**固收**（区间通常最宽），并注明次优解。

---

## Step 6：产品层（引擎，非 Solver）

```python
target_cat, notes = FlagDrivenSolver().solve(...)
product_targets = engine._allocate_products_asset_type(target_cat=target_cat, ...)
# 不调用 _solve_category_targets
```

与一键共用：consolidate、prefer_existing、产品 min/max spill。

---

## 口径差异（排查必读）

| 层级 | idle 怎么处理 |
|------|---------------|
| FlagDrivenSolver | idle **并入** cash 当前值参与求解 |
| smart_one_click | idle **单独字段**，不并入 cash current |
| RebalanceResult | `idle_cash` 仍单独返回 |
| 前端方案态 | 「本次已配置闲置资金」= deltas 汇总，可能与 solver 现金池不一致 |

调整 idle/现金展示时，需同时看 Solver、产品层、PlanEditor，避免只改一处。

---

## 代码常量速查

```text
EQUITY_BLEND_RATIO = 0.5    # 收益低+波动高 时权益折中

SELL_ORDER[收益低]     = 现金, 固收, 另类
BUY_ORDER[收益低]      = 权益, 另类
SELL_ORDER[收益高/本金亏/波动] = 权益, 另类
BUY_ORDER[收益高]      = 现金, 固收
BUY_ORDER[本金亏]      = 固收, 现金
BUY_ORDER[波动]        = 现金, 固收

PASSIVE_BUY  = 固收 → 现金 → 另类 → 权益
PASSIVE_SELL = 另类 → 权益 → 固收 → 现金
```

---

## 辅助函数

```text
to_bench_up   : 低于基准 → 补到基准
to_bench_down : 高于基准 → 收到基准
to_upper_cap  : 高于上限 → 收到上限
hold_in_band  : 在 [floor, hi] 内保持
```

实现以 `flag_driven_solver.py` 为准；本文与代码冲突时以代码为准。
