# 四笔钱智能投顾 API 文档

版本：1.0.0  
Base URL：`http://localhost:8000`

---

## 通用响应格式

```json
{
  "code": 0,
  "message": "ok",
  "data": { ... }
}
```

错误时 HTTP 状态码非 200，`detail` 字段包含错误信息。

---

## 1. 客户资产概览

**GET** `/api/asset/overview`

查询客户首页卡片数据（总资产、健康度、四笔钱卡片、权限）。

### 请求参数

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| customer_id | string | 是 | 客户ID，如 `C20250602001` |
| role | string | 否 | 角色：`advisor`（默认）/ `viewer` |

### 响应示例

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "customer_id": "C20250602001",
    "customer_name": "张女士",
    "risk_profile": "balanced",
    "total_assets": 1012000.0,
    "idle_cash": 150000.0,
    "health": { "level": "yellow", "label": "需关注", "color": "#faad14" },
    "categories": [],
    "permissions": { "can_full_optimize": true }
  }
}
```

---

## 2. 一键智能配仓

**POST** `/api/allocation/auto_rebalance`

### 请求体

```json
{
  "customer_id": "C20250602001",
  "mode": "smart_one_click",
  "target_category": null,
  "locked_categories": [],
  "manual_overrides": {}
}
```

| 字段 | 说明 |
|------|------|
| mode | `smart_one_click` / `manual_tweak` |
| target_category | 单类优化：`spend`/`preserve`/`grow`/`protect` |
| manual_overrides | 人工指定大类目标金额 |

### 使用场景

| 场景 | mode | 其他参数 |
|------|------|----------|
| 全账户一键优化 | smart_one_click | — |
| 单类智能优化 | smart_one_click | target_category=grow |
| 人工微调 | manual_tweak | manual_overrides + locked_categories |

---

## 3. 资产配置模型（页面A）

**GET** `/api/model/list` — 模型列表  
**GET** `/api/model/detail?model_code=P2-3` — 单模型 + 四笔钱聚合阈值  
**POST** `/api/model/save` — 保存 `model_config.yaml`（保留 P1 / P2-2~P2-5）

**GET** `/api/portfolio/map?product_category=投资规划`  
**GET** `/api/allocation/resolve?product_category=投资规划&risk_label=balanced`

## 7. 健康检查

**GET** `/api/health` → `{ "status": "ok", "service": "four-money-advisor" }`

---

## 演示客户

| customer_id | 姓名 | 风险画像 |
|-------------|------|----------|
| C20250602001 | 张女士 | balanced |
| C20250602002 | 李先生 | conservative |
| C20250602003 | 王先生 | aggressive |
