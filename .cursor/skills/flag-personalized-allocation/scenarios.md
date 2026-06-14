# 个性化配仓典型场景

> 算法处方（四类标志怎么算 intent）→ [SKILL.md](SKILL.md) / [algorithm.md](algorithm.md)  
> 本文：**演示客户、UI 操作、预期结果、验证命令**

前提：规划类型 = **投资规划**；智能资配页 `#btnPersonalizedOptimize` 可见；服务端从诊断重新取标志（不信任前端）。

---

## 场景 1：收益不达预期（赵女士 · 稳健型）

| 项 | 内容 |
|----|------|
| 客户 | `C20250602004` 赵女士，risk `prudent`，默认 `loss_3pct` → 投资规划 P2 |
| 有效标志 | `return_below_expected` |
| 操作 | 智能资配 → **个性化智能配仓** |
| 预期方向 | 减现金/固收（若超），权益 **至少基准**，Normalize 优先 **顶满权益上限** 再另类 |
| 验证 | `pytest tests/test_flag_driven.py::TestFlagDrivenSolver::test_return_below_equity_at_least_bench_not_cut -v` |

```bash
curl -s -X POST http://127.0.0.1:8000/api/allocation/auto_rebalance \
  -H "Content-Type: application/json" \
  -d '{"customer_id":"C20250602004","mode":"flag_personalized","product_category":"投资规划"}'
```

---

## 场景 2：收益超预期（张女士 · 平衡型）

| 项 | 内容 |
|----|------|
| 客户 | `C20250602001` 张女士，risk `balanced`，含保障类持仓 |
| 有效标志 | `return_above_expected` |
| 预期方向 | 减权益/另类至基准；现金、固收 **至少基准**，Normalize **先现金后顶满固收上限** |
| 验证 | `pytest tests/test_flag_driven.py::TestFlagDrivenSolver::test_return_above_fixed_anchors_bench -v` |

---

## 场景 3：本金损失超阈值（周先生 · 稳健型 · 纯投资）

| 项 | 内容 |
|----|------|
| 客户 | `C20250602007` 周先生，risk `prudent`，纯投资无保单 |
| 有效标志 | `principal_loss_exceeded` |
| 预期方向 | 减权益/另类，**加满固收与现金**（防守止损） |
| 验证 | `pytest tests/test_flag_driven.py::TestFlagPersonalizedRebalance::test_engine_flag_personalized -v` |

```bash
curl -s -X POST http://127.0.0.1:8000/api/allocation/auto_rebalance \
  -H "Content-Type: application/json" \
  -d '{"customer_id":"C20250602007","mode":"flag_personalized","product_category":"投资规划"}'
```

响应 `validation_notes` 应含 **「个性化配仓依据：…」**；`mode` = `flag_personalized`。

---

## 场景 4：波动率超预期（王先生 · 进取型）

| 项 | 内容 |
|----|------|
| 客户 | `C20250602003` 王先生，risk `aggressive` |
| 有效标志 | `volatility_exceeded` |
| 预期方向 | 减权益/另类，加现金与固收（降波动） |
| 验证 | `pytest tests/test_flag_driven.py -v`（solver 单测 + 引擎回归） |

---

## 场景 5：复合 · 收益高 + 本金亏（刘女士 · 推荐演示）

| 项 | 内容 |
|----|------|
| 客户 | `C20250602006` 刘女士，risk `balanced`，**纯投资** |
| 有效标志 | `return_above_expected` + `principal_loss_exceeded` |
| 合并规则 | **整单按本金亏**（止损优先于止盈） |
| 操作 | 财富盘点 → 资产诊断 → 智能资配；顶部可见两枚标志 → 个性化配仓 |
| 预期 | 大类方向同场景 3；notes 体现本金亏处方，而非单纯收益高 |
| 验证 | `pytest tests/test_flag_driven.py::TestFlagDrivenSolver::test_merge_above_and_principal_prefers_principal -v` |

```bash
python demo_test.py --customer C20250602006
curl -s -X POST http://127.0.0.1:8000/api/allocation/auto_rebalance \
  -H "Content-Type: application/json" \
  -d '{"customer_id":"C20250602006","mode":"flag_personalized","product_category":"投资规划","loss_key":"loss_6pct"}'
```

---

## 场景 6：复合 · 收益高 + 波动高（孙女士 · 推荐演示）

| 项 | 内容 |
|----|------|
| 客户 | `C20250602008` 孙女士，risk `growth`，**纯投资** |
| 有效标志 | `return_above_expected` + `volatility_exceeded` |
| 合并规则 | **整单按波动高**；notes 追加 **「兼考虑收益偏高，权益已收到基准止盈」** |
| 预期方向 | 权益收到基准止盈 + 降波动（加现金/固收） |
| 验证 | `pytest tests/test_flag_driven.py::TestFlagDrivenSolver::test_merge_above_and_volatility_uses_vol_and_note -v` |

```bash
python demo_test.py --customer C20250602008
```

---

## 场景 7：复合 · 收益低 + 波动高（合成 / 单测）

演示 mock 中**无**天然双标志客户；合并规则见 SKILL「收益低 + 波动高」表（权益 50% 折中，Normalize 买序仍用收益低）。

| 验证 | `pytest tests/test_flag_driven.py::TestFlagDrivenSolver::test_merge_below_and_volatility_equity_compromise -v` |

---

## 场景 8：健康客户拒绝

| 项 | 内容 |
|----|------|
| 客户 | `C20250602002` 李先生（无业绩/风险标志，或仅 `four_money_mismatch`） |
| 操作 | 个性化智能配仓 |
| 预期 | HTTP **400**，文案含 **「财富健康，请用全账户一键配仓」** |
| 验证 | `pytest tests/test_flag_driven.py::TestFlagPersonalizedAPI::test_flag_personalized_rejects_healthy_customer -v` |

---

## 场景 9：指定 loss_key（与一键共用模型选择）

| 项 | 内容 |
|----|------|
| 操作 | 工具栏第二行：**投资组合偏好** 或 **预期年化收益** Tab → 选档位（如 `loss_3pct`） |
| API | 请求体带 `"loss_key": "loss_3pct"` |
| 预期 | 阈值来自该 loss_key 对应模型；**只换 band/bench，不换 FlagDrivenSolver 步骤** |
| 验证 | mapping 横幅 + `GET /api/allocation/resolve?product_category=投资规划&risk_label=balanced&loss_key=loss_3pct` |

---

## 场景 10：与全账户一键对比（同一客户）

| 步骤 | 说明 |
|------|------|
| 1 | 选刘女士或孙女士，先 **全账户一键** → 记录 `category_summary` |
| 2 | 再 **个性化智能配仓** → `mode` 必须为 `flag_personalized` |
| 3 | 对比 | 个性化应出现明显 **主动加/减**（非 band 内最小异动）；一键尽量 in_band 少动 |

`pytest tests/test_flag_driven.py::TestFlagPersonalizedRebalance::test_smart_one_click_unchanged` 保证一键路径未被污染。

---

## 场景 11：财富旅程 + AI 顾问演示话术

1. **财富盘点** `wealth_inventory.html` → 点刘女士 / 孙女士行进入诊断  
2. **资产诊断** → 看五维雷达与标志 → **进入智能资配**  
3. **智能资配** → 右侧顾问侧栏（默认展开）→ 「资产诊断解读」或输入追问  
4. 展示 **个性化智能配仓** → 打开方案 → 「AI深度解读」  
5. 强调：标志来自 `_MOCK_PERFORMANCE` + `WealthJourneyService._build_flags`，与模型基准对齐  

顾问侧栏跨页保留对话；流式输出中断后新页 **自动续传**（见 `advisor_chat.js` inflight）。

---

## 演示客户速查

| ID | 姓名 | 有效标志（不含四笔钱） | 推荐用途 |
|----|------|------------------------|----------|
| C20250602004 | 赵女士 | 收益不达预期 | 单场景 · 加仓权益 |
| C20250602001 | 张女士 | 收益超预期 | 单场景 · 止盈（含保障持仓） |
| C20250602007 | 周先生 | 本金亏（未持仓 P000） | 单场景 · API/引擎回归 |
| C20250602003 | 王先生 | 波动高 | 单场景 · 降波动 |
| **C20250602006** | **刘女士** | **收益高 + 本金亏** | **复合 · 优先止损** |
| **C20250602008** | **孙女士** | **收益高 + 波动高** | **复合 · 止盈 + 降波动** |
| C20250602002 | 李先生 | （无） | 拒绝个性化 |
| C20250602005 | 陈先生 | 收益超预期 | 备选单场景 |

模拟业绩：`core/wealth_journey_service.py` → `_MOCK_PERFORMANCE`。

---

## 一键回归

```bash
pytest tests/test_flag_driven.py -v
pytest tests/test_allocation.py -k investment -v
```
