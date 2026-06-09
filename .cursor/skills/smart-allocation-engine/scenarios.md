# 智能配仓典型场景

## 场景 1：全账户一键（张女士 · 平衡型）

- 客户：`C20250602001`，risk `balanced`，模型通常 `P2-3`
- 操作：全账户一键智能最优配置
- 预期：在区间内大类尽量不动；越界大类按 `band_midpoint` 回退
- 验证：`python demo_test.py --customer C20250602001`

## 场景 2：单类优化生钱的钱

- 请求：`target_category: "grow"`
- 业务语义：只调生钱的钱，保值的钱/要花的钱等保持现仓
- 超配生钱的钱 → 减至 equity+alternative 聚合后的 **benchmark**
- 若总资产有缺口 → `validation_notes` 提示未纳入配置金额

## 场景 3：保守型客户触限（李先生）

- 客户：`C20250602002`，conservative
- 常用于测试 consolidate、spillover、min_amount
- 测试：`pytest tests/test_allocation.py -k "C20250602002 or conservative" -v`

## 场景 4：手工添加 0 持仓产品

- 智能一键不会出现 0 持仓新产品
- 流程：方案编辑器 → 添加产品 → `manual_product_edit`
- 校验：剩余可配置闲置 ≥ 起购金额
- API：`GET /api/products/candidates?customer_id=...`

## 场景 5：竞赛演示话术

1. 打开 `smart_allocation.html`，选张女士
2. 展示检视卡片（健康度、大类偏离）
3. 点击「全账户一键智能最优配置」
4. 指出 `in_band` 与 `adjust_amount` 区别
5. 「生成配置解读」+ AI 对话追问「不想卖指数基金怎么办」

## API 请求示例

### 全账户

```bash
curl -s -X POST http://127.0.0.1:8000/api/allocation/auto_rebalance \
  -H "Content-Type: application/json" \
  -d '{"customer_id":"C20250602001","mode":"smart_one_click"}'
```

### 单类

```bash
curl -s -X POST http://127.0.0.1:8000/api/allocation/auto_rebalance \
  -H "Content-Type: application/json" \
  -d '{"customer_id":"C20250602001","mode":"smart_one_click","target_category":"grow"}'
```

### 解析阈值（配仓前）

```bash
curl -s "http://127.0.0.1:8000/api/allocation/resolve?product_category=投资规划&risk_label=balanced"
```
