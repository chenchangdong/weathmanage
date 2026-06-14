---
name: four-money-rules
description: >-
  Configures 四笔钱 (four-money) business rules for the weathmanage wealth-advisor
  workbench via YAML. Covers risk-to-model mapping, asset thresholds, product
  constraints, solver flags, and UI/permission rules. Use when changing 四笔钱
  thresholds, risk mapping, model config, product limits, health badge rules,
  page permissions, or asking which config file drives a business behavior.
---

# 四笔钱业务规则配置

## 一句话

**不改代码**就能调整：客户风险怎么对应模型、各大类占比区间、产品限额、求解器默认策略、页面展示与按钮权限。

## 业务概念

| 术语 | 含义 |
|------|------|
| 四笔钱 | spend 要花的 / preserve 保值 / grow 生钱 / protect 保障 |
| 五档风险 | conservative … aggressive |
| 投资组合偏好 | loss_1pct … loss_15pct，与风险档映射 |
| 目标模型 | P1、P2-2 … P2-5，每模型五类 asset_limit |
| asset_limit | `[下限%, 基准%, 上限%]`（YAML 里是百分数，引擎用小数） |
| 生钱的钱 | 权益 + 另类聚合；上限 = min(权益上限+另类基准, 100%) |

## 配置链路（从客户到引擎）

```text
客户 risk_profile
    ↓
portfolio_mapping.yaml（风险 → loss_key → target_model）
    ↓
model_config.yaml（模型 asset_limit）
    ↓
four_money_mapping.yaml（资产类型 → 四笔钱，grow 聚合规则）
    ↓
AllocationConfigService.resolve_*_targets(..., loss_key?)
    ↓
引擎 targets: { target, band }
```

### 规划类型两条 resolve 路径

| 规划类型 | 方法 | 卡片维度 |
|----------|------|----------|
| 投资规划 | `resolve_asset_type_targets` | 现金/固收/权益/另类 |
| 综合规划 | `resolve_profile_targets` | 四笔钱 |

### 用户覆盖模型（loss_key）

智能资配页可选「投资组合偏好 / 预期年化收益」档位 → 请求带 `loss_key`：

```text
get_model_by_customer_risk(category, risk, loss_key=用户选择)
  → 跳过 risk 默认映射，直接用该 loss_key 查 portfolio_map
```

**只换模型与阈值，不改求解算法。** 前端：`js/model_selector.js`。

验证：

```bash
curl "http://127.0.0.1:8000/api/allocation/resolve?product_category=投资规划&risk_label=balanced"
curl "http://127.0.0.1:8000/api/allocation/resolve?product_category=投资规划&risk_label=balanced&loss_key=loss_3pct"
```

## 改什么 → 改哪个文件

| 业务变更 | 文件 | 关键字段 |
|----------|------|----------|
| 大类名称 / 求解器开关 | `four_money_rule.yaml` | categories, solver |
| 资产类型 → 四笔钱 | `four_money_mapping.yaml` | four_money_rule, category_code_map |
| 模型阈值 P1/P2-x | `model_config.yaml` | model_list.*.asset_limit |
| 风险 → 模型映射 | `portfolio_mapping.yaml` | customer_risk_levels, portfolio_map, risk_loss_default |
| 产品起购/上限/优先级 | `product_constraint.yaml` | products, rebalance_priority |
| 首页健康度文案 | `four_money_page.yaml` | health_thresholds |
| 按钮权限 | `page_constraint.yaml` | roles, buttons |
| 演示客户 | `customer_profile.yaml` | demo_customers |
| 演示持仓 | `core/data_store.py` | DEMO_HOLDINGS |

YAML 索引 → [reference.md](reference.md)

## 求解器参数（改策略优先改 YAML）

位于 `four_money_rule.yaml` → `solver`，驱动 **smart_one_click** 大类求解（不是 flag 个性化）：

| 参数 | 白话 |
|------|------|
| `minimize_cash_movement` | 在区间内就不动 |
| `fallback_strategy` | 越界回哪：benchmark / band_midpoint / band_low / band_high |
| `consolidate_category_rebalance` | 类内一只主产品承接 |
| `prefer_existing_holdings` | 非集中时按现仓比例分 |
| `liquidate_below_min` | 允许卖到 0 |
| `max_iterations` | 产品触顶冻结重算轮数 |

算法怎么执行 → `smart-allocation-engine/algorithm.md`

## 配置后台

| 页面 | API | 写入 |
|------|-----|------|
| 模型配置 | POST /api/model/save | model_config.yaml |
| 模型指派 | POST /api/portfolio/map/save | portfolio_mapping.yaml |

保存后 `reload_all_configs()`，**无需重启**。手改 YAML 需重启或手动 reload。

## 不变式（改完必查）

1. 5 个模型：P1, P2-2 … P2-5  
2. 五档风险与 loss_1pct … loss_15pct 可映射  
3. 投资规划、综合规划在 portfolio_map 中均有条目  
4. 产品 asset_type 能映射到四笔钱  
5. asset_limit：下限 ≤ 基准 ≤ 上限  

`pytest tests/test_model_config.py -v`

## 常见变更

### 调整某风险档的生钱的钱上限

1. resolve 查模型：`GET /api/allocation/resolve?risk_label=balanced`
2. 改 `model_config.yaml` 中 equity/alternative 的 asset_limit
3. 生钱上限 = min(权益上限+另类基准, 100%)
4. 再 resolve 验证

### 新增演示客户

1. `customer_profile.yaml` 加 demo_customers  
2. `data_store.py` 加同 ID 持仓  
3. `python demo_test.py --customer <新ID>`

### 调整「在区间内不动」

改 `four_money_rule.yaml` → `solver.minimize_cash_movement` 或 `fallback_strategy`。

## 边界

| Skill | 分工 |
|-------|------|
| `smart-allocation-engine` | 配仓怎么算、结果怎么读 |
| `flag-personalized-allocation` | 标志驱动配仓（独立求解） |
| `llm_config.yaml` | 大模型，非四笔钱底座 |

## 验证

```bash
pytest tests/test_model_config.py -v
python demo_test.py --customer C20250602001
```

演示客户：张女士 C20250602001 / 李先生 C20250602002 / 王先生 C20250602003
