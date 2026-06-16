# 个性化智能配仓（新）典型场景

> 算法说明 → [SKILL.md](SKILL.md) / [algorithm.md](algorithm.md)  
> 本文：**演示客户、UI 操作、与旧版/一键的差异、验证命令**

前提：规划类型 = **投资规划**；`#btnOptimalPersonalized` 可见；**不要求**财富健康标志。

---

## 场景 1：财富健康客户（李先生 · 无标志）

| 项 | 内容 |
|----|------|
| 客户 | `C20250602002` 李先生 |
| 有效标志 | 无（或仅 `four_money_mismatch`） |
| 旧版个性化 | 前端/服务端拒绝「财富健康，请用全账户一键配仓」 |
| 本模式 | **可正常发起** |
| 操作 | 智能资配 → **个性化智能配仓（新）** |
| 预期 | `mode=optimal_personalized`；大类按模型最优；产品全 hold |

```bash
curl -s -X POST http://127.0.0.1:8000/api/allocation/auto_rebalance \
  -H "Content-Type: application/json" \
  -d '{"customer_id":"C20250602002","mode":"optimal_personalized","product_category":"投资规划"}'
```

```bash
pytest tests/test_flag_driven.py::TestOptimalPersonalizedRebalance::test_optimal_personalized_api_success_without_flags -v
```

---

## 场景 2：与全账户一键大类一致、产品层不同

| 项 | 内容 |
|----|------|
| 客户 | 任意投资规划客户 |
| 对比 | 先 `#btnFullOptimize`，再 `#btnOptimalPersonalized` |
| 大类 | `category_targets` / `category_summary.adjust_amount` 应与一键 **一致**（同 solver 入参） |
| 产品 | 一键已有买卖；新模式首次 **全 hold** |
| 落实 | 新模式逐类「一键自动调仓」后，该类产品建议与一键该类接近（同 `_allocate_products_asset_type`） |

---

## 场景 3：与旧版个性化大类不同（有标志客户）

| 项 | 内容 |
|----|------|
| 客户 | `C20250602007` 周先生（`principal_loss_exceeded`） |
| 操作 | 分别发起 `flag_personalized` 与 `optimal_personalized` |
| 预期 | 两类 `category_summary` 的 `target_amount` **不应相同** |
| 原因 | 旧版按标志处方；新版按最小异动最优 |

```bash
pytest tests/test_flag_driven.py::TestOptimalPersonalizedRebalance::test_optimal_differs_from_flag_when_both_available -v
```

---

## 场景 4：分步落实产品（UX 与旧版相同）

| 步骤 | 操作 |
|------|------|
| 1 | 进入配置方案，查看各大类「现仓 → 处方目标」 |
| 2 | 对需调整大类点 **一键自动调仓** |
| 3 | 微调产品增减仓 |
| 4 | 手工改过后按钮变 **一键还原配仓**；还原后恢复 **一键自动调仓** |
| 5 | 刷新/返回后处方从 `sessionStorage.categoryPrescription` 恢复 |

共用 API：`POST /allocation/flag_category_suggest`、`POST /allocation/manual_adjust`

---

## 场景 5：综合规划应拒绝

```bash
curl -s -X POST http://127.0.0.1:8000/api/allocation/auto_rebalance \
  -H "Content-Type: application/json" \
  -d '{"customer_id":"C20250602001","mode":"optimal_personalized","product_category":"综合规划"}'
```

预期：400，`detail` 含「投资规划」。

```bash
pytest tests/test_flag_driven.py::TestOptimalPersonalizedRebalance::test_optimal_personalized_rejects_comprehensive_planning -v
```

---

## 场景 6：切换 loss_key / 追加持仓

| 项 | 说明 |
|----|------|
| loss_key | 与一键相同，影响 `profile_targets` band |
| idle_cash | 并入 cash current 再求解；处方冻结 total 含 idle |
| 追加持仓变化 | 与旧版个性化相同：`promptRegeneratePrescription` 或丢弃不可恢复缓存 |

---

## 模式选择速查

| 客户状态 | 推荐 mode |
|----------|-----------|
| 财富健康，要一次配满产品 | `smart_one_click` |
| 财富健康，要分步落实 | **`optimal_personalized`** |
| 有收益/风险标志，按病征调大类 | `flag_personalized` |
| 有标志，但要最优大类 + 分步落实 | **`optimal_personalized`**（大类会与 flag 不同） |

---

## 完整测试

```bash
pytest tests/test_flag_driven.py::TestOptimalPersonalizedRebalance -v
pytest tests/test_flag_driven.py::TestFlagPersonalizedRebalance::test_smart_one_click_unchanged -v
```
