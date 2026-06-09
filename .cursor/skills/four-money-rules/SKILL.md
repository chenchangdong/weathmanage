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

## 业务能力定义

为理财经理工作台提供**可配置、不改代码**的四笔钱业务底座：客户风险如何映射到模型、各大类占比区间从哪来、产品能买多少、求解器默认策略、首页展示与按钮权限。

## 业务概念词典

| 术语 | 含义 |
|------|------|
| 四笔钱 | `spend`要花的钱 / `preserve`保值的钱 / `grow`生钱的钱 / `protect`保障的钱 |
| 五档风险 | `conservative`保守 … `aggressive`进取（共 5 档） |
| 投资组合偏好 | `loss_1pct`…`loss_15pct`，与客户风险一一对应 |
| 目标模型 | `P1`、`P2-2`…`P2-5`，每模型有五类 `asset_limit` |
| asset_limit | `[下限%, 基准%, 上限%]`，百分比非小数 |
| 生钱的钱聚合 | 权益+另类合并；基准=权益基准+另类基准；上限封顶 100% |

## 配置链路（业务 → 技术）

```
客户 risk_profile
  → portfolio_mapping.yaml（风险 → loss_key → target_model）
  → model_config.yaml（模型 asset_limit）
  → four_money_mapping.yaml（资产类型 → 四笔钱 + 聚合规则）
  → AllocationConfigService.calc_four_money_threshold()
  → 引擎 targets: { target: 基准/100, band: [下/100, 上/100] }
```

验证链路：`GET /api/allocation/resolve?product_category=投资规划&risk_label=balanced`

## 改什么业务 → 改哪个文件

| 业务变更 | 配置文件 | 关键字段 |
|----------|----------|----------|
| 大类名称/图标/求解器开关 | `config/four_money_rule.yaml` | `categories`, `solver` |
| 资产类型归属四笔钱 | `config/four_money_mapping.yaml` | `four_money_rule`, `category_code_map` |
| 模型阈值（P1/P2-x） | `config/model_config.yaml` | `model_list.*.asset_limit` |
| 风险五档 → 模型 | `config/portfolio_mapping.yaml` | `customer_risk_levels`, `portfolio_map` |
| 产品起购/上限/优先级 | `config/product_constraint.yaml` | `products`, `rebalance_priority` |
| 首页健康度颜色/文案 | `config/four_money_page.yaml` | `health_thresholds`, labels |
| 按钮权限（顾问/viewer） | `config/page_constraint.yaml` | `roles`, `buttons` |
| 演示客户画像 | `config/customer_profile.yaml` | `demo_customers` |
| 客户持仓（演示数据） | `core/data_store.py` | `DEMO_HOLDINGS`（须与 profile 同步） |

详细 YAML 索引见 [reference.md](reference.md)。

## 求解器参数（four_money_rule.yaml → solver）

这些参数驱动智能配仓引擎，改业务策略时优先改 YAML，勿改 `auto_rebalance_engine.py`：

| 参数 | 业务含义 |
|------|----------|
| `minimize_cash_movement` | 大类已在区间内 → 保持现仓不动 |
| `fallback_strategy` | 全账户越界时的回退落点：`benchmark` / `band_midpoint` / `band_low` / `band_high` |
| `consolidate_category_rebalance` | 类内集中调仓：优先级最高产品承接增减，触限 spill |
| `prefer_existing_holdings` | consolidate=false 时按持仓占比分摊 |
| `liquidate_below_min` | 可减至 0（触下限时清仓语义） |

## 配置后台保存

| 页面 | API | 写入文件 |
|------|-----|----------|
| 模型配置 | `POST /api/model/save` | `model_config.yaml` |
| 风险映射 | `POST /api/portfolio/map/save` | `portfolio_mapping.yaml` |

保存后自动 `reload_all_configs()`，**无需重启**。

直接手改 YAML 文件：需重启服务，或在 Python 中调用 `reload_all_configs()`。

## 不变式（改配置后必查）

1. 恰好 5 个模型：`P1`, `P2-2`, `P2-3`, `P2-4`, `P2-5`
2. 五档风险与 `loss_1pct`…`loss_15pct` 一一映射
3. 当前仅 `投资规划` 一个 `product_category`
4. 产品 `asset_type` 必须能映射到四笔钱
5. `asset_limit` 满足 下限 ≤ 基准 ≤ 上限

运行：`pytest tests/test_model_config.py -v`

## 常见业务变更流程

### 调整某风险档位的生钱的钱上限

1. 查该档对应模型：`GET /api/allocation/resolve?risk_label=balanced`
2. 改 `model_config.yaml` 中该模型的 `equity` / `alternative` 的 `asset_limit`
3. 记住生钱的钱上限 = `min(权益上限 + 另类基准, 100%)`
4. 验证 resolve 接口与生钱的钱阈值

### 新增演示客户

1. `customer_profile.yaml` 增加 `demo_customers` 条目（`risk_profile` 为五档之一）
2. `core/data_store.py` 增加同 ID 的 `DEMO_HOLDINGS`
3. `python demo_test.py --customer <新ID>`

### 调整「在区间内不动」策略

改 `four_money_rule.yaml` → `solver.minimize_cash_movement` 或 `fallback_strategy`。

## 验证与演示

```bash
# 配置链路
curl "http://127.0.0.1:8000/api/allocation/resolve?product_category=投资规划&risk_label=balanced"

# 模型不变式
pytest tests/test_model_config.py -v

# 端到端
python demo_test.py --customer C20250602001
```

演示客户：张女士 `C20250602001` balanced / 李先生 `C20250602002` conservative / 王先生 `C20250602003` aggressive。

## 边界

- 本 Skill 只管**规则从哪来、怎么改、怎么生效**
- 配仓怎么算、结果怎么读 → 使用 `smart-allocation-engine` Skill
- LLM 对话配置 → `config/llm_config.yaml`（不属于四笔钱规则底座）
