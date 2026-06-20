---
name: four-money-rules
description: >-
  Configures 四笔钱 (four-money) business rules for the wealthmanagement wealth-advisor
  workbench via YAML. Covers risk-to-model mapping, asset thresholds, product
  constraints, solver flags, and UI/permission rules. Use when changing 四笔钱
  thresholds, risk mapping, model config, product limits, health badge rules,
  page permissions, or asking which config file drives a business behavior.
---

# 四笔钱业务规则

## 产品定位

**把「客户该怎么配」变成可配置、可复用的业务底座。**

理财经理看到的大类区间、模型指派、产品限额、页面按钮权限，都来自同一套规则配置——**改规则不必改代码**，后台保存即生效。

## 业务概念

| 术语 | 含义 |
|------|------|
| 四笔钱 | 要花的 / 保值的 / 生钱的 / 保障的 |
| 五档风险 | 保守型 … 进取型 |
| 投资组合偏好 | 可承受亏损档位，与风险档映射 |
| 目标模型 | P1、P2-2 … P2-5，每模型五类资产区间 |
| 资产区间 | 下限、基准、上限（引擎内部用小数） |
| 生钱的钱 | 权益 + 另类聚合 |

## 配置链路（从客户到配仓）

```text
客户风险等级
    ↓
风险 → 模型映射（portfolio_mapping）
    ↓
模型阈值（model_config）
    ↓
资产类型 → 四笔钱（four_money_mapping）
    ↓
配仓引擎读取 targets: { target, band }
```

### 两种规划类型

| 规划类型 | 卡片维度 |
|----------|----------|
| 投资规划 | 现金 / 固收 / 权益 / 另类 |
| 综合规划 | 四笔钱 |

### 用户覆盖模型

智能资配页可选「投资组合偏好 / 预期年化收益」→ 请求带 `loss_key`，**只换模型阈值，不换求解算法**。前端：`js/model_selector.js`。

## 改什么 → 改哪个文件

| 业务变更 | 文件 |
|----------|------|
| 大类名称 / 求解策略 | `four_money_rule.yaml` |
| 资产类型 → 四笔钱 | `four_money_mapping.yaml` |
| 模型阈值 | `model_config.yaml` |
| 风险 → 模型映射 | `portfolio_mapping.yaml` |
| 产品起购/上限/优先级 | `product_constraint.yaml` |
| 首页健康度文案 | `four_money_page.yaml` |
| 按钮权限 | `page_constraint.yaml` |
| 演示客户 | `customer_profile.yaml` |

YAML 索引 → [reference.md](reference.md)

## 求解器策略（智能配仓默认）

位于 `four_money_rule.yaml` → `solver`：

| 参数 | 业务含义 |
|------|----------|
| `minimize_cash_movement` | 已在区间内尽量不动 |
| `fallback_strategy` | 越界时回退到基准/区间端点 |
| `consolidate_category_rebalance` | 类内一只主产品承接 |
| `prefer_existing_holdings` | 优先在现有持仓间分配 |
| `liquidate_below_min` | 允许卖到 0 |
| `max_iterations` | 产品触顶后重算轮数 |

算法细节 → `smart-allocation-engine/algorithm.md`

## 配置后台

| 页面 | 写入 |
|------|------|
| 模型建立 | `model_config.yaml` |
| 模型指派 | `portfolio_mapping.yaml` |

保存后自动 reload，**无需重启**。

## 不变式（改完必查）

1. 5 个模型：P1, P2-2 … P2-5
2. 五档风险与 loss 档位可映射
3. 投资规划、综合规划均有映射条目
4. 产品 asset_type 能映射到四笔钱
5. 区间：下限 ≤ 基准 ≤ 上限

`pytest tests/test_model_config.py -v`

## 与其他 Skill 的分工

| Skill | 分工 |
|-------|------|
| `smart-allocation-engine` | 配仓怎么算、结果怎么读 |
| `flag-personalized-allocation` | 标志驱动配仓 |
| `optimal-personalized-allocation` | 最优大类 + 分步落实 |

## 验证

```bash
pytest tests/test_model_config.py -v
python demo_test.py --customer C20250602001
```
