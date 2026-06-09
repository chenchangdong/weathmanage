# 四笔钱配置参考

## YAML 文件一览

| 文件 | 版本字段 | 主要职责 |
|------|----------|----------|
| `four_money_rule.yaml` | 1.1 | 四笔钱大类定义 + 求解器 solver |
| `four_money_mapping.yaml` | 1.0 | 资产类型 → 四笔钱 + grow 聚合 |
| `model_config.yaml` | — | P1/P2-x 模型与 asset_limit |
| `portfolio_mapping.yaml` | — | 五档风险、portfolio_map |
| `product_constraint.yaml` | — | 产品清单与买卖约束 |
| `four_money_page.yaml` | — | 首页卡片与健康度 |
| `page_constraint.yaml` | — | 角色与按钮权限 |
| `customer_profile.yaml` | — | 风险等级说明 + 演示客户 |
| `aftercare_rule.yaml` | — | 投后陪伴（非配仓底座） |
| `llm_config.yaml` | 1.0 | 大模型（非四笔钱规则） |

## 引擎 category code 对照

| YAML key (four_money_mapping) | 引擎 code | 中文名 |
|-------------------------------|-----------|--------|
| need_spend | spend | 要花的钱 |
| keep_value | preserve | 保值的钱 |
| grow_asset | grow | 生钱的钱 |
| secure_money | protect | 保障的钱 |

## asset_type 对照

| asset_type | 别名 | 默认四笔钱 |
|------------|------|------------|
| cash | 现金类 | spend |
| fixed_income | 固收类 | preserve |
| equity | 权益类 | grow（与 alternative 聚合） |
| alternative | 另类及其他 | grow（与 equity 聚合） |
| insurance | 保障类 | protect |

## grow_equity_alt 聚合公式

```
下限 = equity.lower
基准 = equity.benchmark + alternative.benchmark
上限 = min(equity.upper + alternative.benchmark, 100)
```

实现：`core/allocation_config_service.py` → `_aggregate_category_threshold`

## portfolio_mapping 结构要点

```yaml
customer_risk_levels:
  - code: balanced
    loss_key: loss_6pct
portfolio_map:
  投资规划:
    loss_6pct:
      target_model: P2-3
```

## 缓存与热加载

- 所有 loader 使用 `@lru_cache`
- 管理后台 API 保存 → `core/config_writer.py` → `reload_all_configs()`
- 引擎初始化会 `load_four_money_rule.cache_clear()`
