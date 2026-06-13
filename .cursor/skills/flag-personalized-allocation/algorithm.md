# 个性化配仓 — 归一化与求解伪代码

本文档为 `flag-personalized-allocation` Skill 的算法细节附录。实现以 `asset_allocation/flag_driven_solver.py` 为准。

## 符号

```text
total     = Σ current_cat[产品持仓] + idle_cash
cur[c]    = 当前类金额（cash 含 idle：cur[cash] = 产品现金 + idle_cash）
bench[c]  = profile_targets[c].target * total
lo[c]     = band[0] * total
hi[c]     = band[1] * total
floor[c]  = max(bench, lo) 若 c=cash，否则 lo[c]
intent[c] = 合并场景后的意图金额
tgt[c]    = 归一化后最终大类目标
diff      = total - Σ tgt[c]
ε         = 0.01 元
```

## Phase A — 合并 intent

```python
effective = {code for code in flag_codes if code in PERFORMANCE_FLAG_CODES}
if not effective:
    raise FlagDrivenSolverError("财富健康，请用全账户一键配仓")

cur = cash_pool(current_cat, idle_cash)  # cash += idle
bounds = per_class_bounds(profile_targets, total)
dominant = dominant_scenario(effective)   # 本金亏 > 收益高 > 收益低 > 波动

intent, passive = merged_intents(effective, cur, total, bounds)
# passive: 本轮「主动不动」的类，Phase E 可被动吸收

for cat in CATS:
    intent[cat] = clamp(intent[cat], floor[cat], hi[cat])
```

### `_scenario_intents(scenario, cur, bounds)`

```python
if scenario == "return_below_expected":
    intent[cash]   = to_bench_down(cur[cash])
    intent[fixed]  = to_upper_cap(cur[fixed])
    intent[equity] = hi[equity]
    intent[alt]    = hold_in_band(cur[alt])

if scenario == "return_above_expected":
    intent[cash]   = to_bench_up(cur[cash])
    intent[fixed]  = hi[fixed]
    intent[equity] = to_bench_down(cur[equity])
    intent[alt]    = lo[alt]

if scenario == "principal_loss_exceeded":
    intent[cash]   = to_bench_up(cur[cash])
    intent[fixed]  = hi[fixed]
    intent[equity] = lo[equity]
    intent[alt]    = to_bench_down(cur[alt])

if scenario == "volatility_exceeded":
    intent[cash]   = to_bench_up(cur[cash])
    intent[fixed]  = to_bench_up(cur[fixed])
    intent[equity] = to_bench_down(cur[equity])
    intent[alt]    = to_bench_down(cur[alt])
```

### `_merged_intents` 决策树

```python
if "return_above" in codes and "principal_loss" in codes:
    return scenario_intents("return_above")

if "return_below" in codes and "principal_loss" in codes:
    return scenario_intents("principal_loss")

if "return_below" in codes and "volatility" in codes:
    base = scenario_intents("volatility")
    base[equity] = clamp(
        bench[equity] + (hi[equity] - bench[equity]) * 0.5,
        floor[equity], hi[equity]
    )
    return base

if "principal_loss" in codes and "volatility" in codes:
    s3 = scenario_intents("principal_loss")
    s4 = scenario_intents("volatility")
    merged = s3
    for c in (equity, alt):
        merged[c] = min(s3[c], s4[c])
    return merged

if "return_above" in codes and "volatility" in codes:
    return scenario_intents("return_above")

if len(codes) == 1:
    return scenario_intents(single_code)

return scenario_intents(dominant_scenario(codes))
```

## Phase B — 另类让路

```python
need = max(0, intent[equity] - cur[equity])
if need <= ε:
    return intent

alt_release = min(
    need,
    max(0, intent[alt] - floor[alt]),
    max(0, cur[alt] - floor[alt]),
)
if alt_release > ε:
    intent[alt] -= alt_release
    intent[equity] = min(hi[equity], intent[equity] + alt_release)

if intent[equity] < hi[equity] - ε:
    intent[alt] = min(intent[alt], hold_in_band(cur[alt]))
```

**语义**：权益未达目标前，另类不得占用增配额度；必要时从另类减配腾给权益。

## Phase C — 初始化 tgt

```python
tgt = {c: round(intent[c], 2) for c in CATS}
diff = round(total - sum(tgt.values()), 2)
```

## Phase D — 主动凑平

```python
if diff > ε:  # 需增配
    for cat in BUY_ORDER[dominant]:
        if diff <= ε: break
        cap = hi[cat] - tgt[cat]
        add = min(diff, cap)
        tgt[cat] += add
        diff -= add

elif diff < -ε:  # 需减配
    need = -diff
    for cat in SELL_ORDER[dominant]:
        if need <= ε: break
        cap = tgt[cat] - floor[cat]   # cash 的 floor = 基准
        cut = min(need, cap)
        tgt[cat] -= cut
        need -= cut
        diff += cut
```

## Phase E — 被动吸收

主动凑平后 `|diff| > ε` 时：

```python
order = PASSIVE_BUY_ORDER if diff > 0 else PASSIVE_SELL_ORDER
# PASSIVE_BUY:  fixed → cash → alt → equity
# PASSIVE_SELL: alt → equity → fixed → cash

for cat in order:
    if diff > 0:
        add = min(diff, hi[cat] - tgt[cat])
        tgt[cat] += add; diff -= add
    else:
        cut = min(-diff, tgt[cat] - floor[cat])
        tgt[cat] -= cut; diff += cut
```

被动池中「本轮主动不动」的类（`passive` 集合）在 notes 中标记为「被动吸收」。

## Phase F — 残差 spill

```python
if |diff| > ε:
    # 默认归入固收（band 最宽）
    if diff > 0:
        tgt[fixed] += min(diff, hi[fixed] - tgt[fixed])
    else:
        tgt[fixed] -= min(-diff, tgt[fixed] - floor[fixed])
    append_note("模型区间内无法完全满足标志配仓意图，已取次优解")
```

## 产品层（引擎侧，非 Solver）

```python
target_cat, flag_notes = FlagDrivenSolver().solve(...)
product_targets, notes, limits = engine._allocate_products_asset_type(
    target_cat=target_cat,
    current_holdings=invest_holdings,
    ...
)
# 与 smart_one_click 共用 consolidate / prefer_existing / spill 规则
# 不调用 _solve_category_targets
```

## 辅助函数

```python
def to_bench_up(cur, b):
    return b["bench"] if cur < b["bench"] - ε else cur

def to_bench_down(cur, b):
    return b["bench"] if cur > b["bench"] + ε else cur

def to_upper_cap(cur, b):
    return b["hi"] if cur > b["hi"] + ε else cur

def hold_in_band(cur, b):
    return clamp(cur, b["floor"], b["hi"])
```

## 已知口径注意

- 求解器 **cash 总池含 idle**；产品层 `_allocate_products_asset_type` 按 **大类 target 金额** 在现金类产品间分摊，**idle 仍单独存在于 `RebalanceResult.idle_cash`**。
- 前端「本次已配置闲置资金」= `sum(product_deltas.delta_amount)`，与 cash 总池 / idle 口径不一致时可能出现显示异常；调整时需同时考虑 Solver 与产品层/前端统计口径（参见 smart-allocation-engine Skill）。
