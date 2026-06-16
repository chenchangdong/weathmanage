# 智能配仓典型场景

> 引擎算法 → [algorithm.md](algorithm.md)  
> 标志驱动个性化 → [../flag-personalized-allocation/scenarios.md](../flag-personalized-allocation/scenarios.md)

主工作台：`frontend/smart_allocation_setup.html`（配置）→ `frontend/smart_allocation.html`（配仓）。导航「智能资配」默认进入配置页。

---

## 场景 1：财富旅程全链路（刘女士 · 纯投资）

| 步骤 | 页面 | 操作 |
|------|------|------|
| 1 | 财富盘点 | 点 **刘女士** 行 → 进入诊断 |
| 2 | 资产诊断 | 查看标志：**收益超预期 + 本金损失超阈值** → **进入智能资配** |
| 3 | 智能资配 | 规划类型 **投资规划**；工具栏见标志与 **个性化智能配仓** |

顾问侧栏：桌面端默认展开，跨页保留对话；输出中跳转可 **续传** 大模型流。

---

## 场景 2：全账户一键（张女士 · 平衡型 · 投资规划）

| 项 | 内容 |
|----|------|
| 客户 | `C20250602001`，risk `balanced`，默认 `loss_6pct` → 投资规划 P3 |
| 操作 | 规划类型 **投资规划** → **全账户一键智能配仓** |
| 预期 | band 内大类尽量不动；越界按 `band_midpoint` 回退 |
| 验证 | `python demo_test.py --customer C20250602001` |

```bash
curl -s -X POST http://127.0.0.1:8000/api/allocation/auto_rebalance \
  -H "Content-Type: application/json" \
  -d '{"customer_id":"C20250602001","mode":"smart_one_click","product_category":"投资规划","loss_key":"loss_6pct","idle_cash":0}'
```

---

## 场景 3：模型选择（投资组合偏好 / 预期年化收益）

| 项 | 内容 |
|----|------|
| UI | 工具栏 **第三行**：Tab **投资组合偏好** \| **预期年化收益**（互斥）+ 下拉（宽 220px，与客户/规划类型下拉对齐） |
| 操作 | 选 Tab → 选档位（如 `loss_3pct` / 对应收益 %） |
| API | 检视、一键、个性化、手工微调均带 `loss_key`（`model_selector.js` → `withLossKey`） |
| 预期 | 阈值与 `GET /api/allocation/resolve?...&loss_key=loss_3pct` 一致；**不换求解算法** |
| 重置 | 每次进入智能资配页恢复该客户 risk 默认档位（不持久化 Tab） |

---

## 场景 4：追加持仓（万单位）

| 项 | 内容 |
|----|------|
| UI | 工具栏 **追加持仓** 与 **财富健康标志** 右列对齐 |
| 操作 | 打开 **追加持仓** 开关后输入 `50` 表示 **50 万**；关闭开关视为无追加持仓 |
| 预期 | 开关打开且录入后 API `idle_cash=500000`；总资产含追加持仓 |
| 口径 | 投资规划→并入 **cash** current；综合规划→并入 **spend** current（均 **不** 调用 FlagDrivenSolver） |
| 全在 band 内 | 追加持仓留在活钱类，固收/权益等不动（如李先生 C002 + 10 万） |
| 注意 | `sessionStorage` 存 **元**；页面显示 **万** |
| 验证 | `pytest tests/test_allocation.py::TestIdleCashAddon -v` |

---

## 场景 5：单类优化 · 生钱的钱（综合规划）

| 项 | 内容 |
|----|------|
| 规划类型 | **综合规划** |
| 请求 | `target_category: "grow"` |
| 语义 | 只调生钱的钱，其余大类冻结现仓 |
| 超配 | 减至聚合 benchmark；缺口见 `validation_notes` |

---

## 场景 6：单类优化 · 权益类（投资规划）

| 项 | 内容 |
|----|------|
| 规划类型 | **投资规划** |
| 请求 | `target_category: "equity"` |
| 语义 | 现金/固收/另类保持现仓，只调权益 |

---

## 场景 7：保守型触限（李先生）

| 客户 | `C20250602002`，conservative |
| 测 | consolidate、spill、`min_amount` |
| 验证 | `pytest tests/test_allocation.py -k "C20250602002 or conservative" -v` |

---

## 场景 8：个性化配仓（见专属 Skill）

| 客户 | 用途 |
|------|------|
| **刘女士** `C20250602006` | 复合：收益高 + 本金亏 → 优先止损 |
| **孙女士** `C20250602008` | 复合：收益高 + 波动高 → 止盈 + 降波动 |
| **周先生** `C20250602007` | 单标志本金亏 · API/引擎回归 |
| **李先生** `C20250602002` | 健康客户 → 400 拒绝 |

完整步骤、curl、pytest → **[flag-personalized-allocation/scenarios.md](../flag-personalized-allocation/scenarios.md)**

```bash
curl -s -X POST http://127.0.0.1:8000/api/allocation/auto_rebalance \
  -H "Content-Type: application/json" \
  -d '{"customer_id":"C20250602006","mode":"flag_personalized","product_category":"投资规划"}'
```

---

## 场景 9：手工添加 0 持仓产品

| 项 | 内容 |
|----|------|
| 限制 | 智能一键不会在 0 持仓产品上新建仓 |
| 流程 | 生成方案 → 方案编辑器 → **选择产品** → `manual_product_edit` |
| API | `GET /api/products/candidates?category=...` |

---

## 场景 10：工具栏布局（智能资配页）

四列网格（`smart-alloc-toolbar`）：

```text
选择客户：  [220px 下拉]    财富健康标志：  [徽章…]
规划类型：  [220px 下拉]    追加持仓：      [ⓘ] [0] 万
[投资组合偏好 | 预期年化收益]  [模型下拉 220px]
```

窄屏（≤720px）自动折行。

---

## 场景 11：竞赛 / 路演话术（15 分钟）

1. 打开 **财富盘点** → 选 **刘女士**（复合标志）  
2. **资产诊断** → 五维 + 标志解读（顾问：**资产诊断解读**）  
3. **智能资配** → 展示 mapping 横幅、四笔钱卡片、`in_band` / `adjust_amount`  
4. 演示 **模型 Tab**（偏好 vs 收益）→ **全账户一键**  
5. 对比 **个性化智能配仓**（强调与一键不同求解器）  
6. **AI深度解读** + 顾问自由追问（侧栏对话跨页保留）  
7. 可选：**追加持仓 50 万** → 重算方案  

---

## API 速查

### 解析阈值

```bash
curl -s "http://127.0.0.1:8000/api/allocation/resolve?product_category=投资规划&risk_label=balanced"
curl -s "http://127.0.0.1:8000/api/allocation/resolve?product_category=投资规划&risk_label=balanced&loss_key=loss_3pct"
```

### 模型映射

```bash
curl -s "http://127.0.0.1:8000/api/portfolio/map?product_category=投资规划"
```

### 资产检视（含 loss_key）

```bash
curl -s "http://127.0.0.1:8000/api/asset/overview?customer_id=C20250602006&loss_key=loss_6pct"
```

---

## 演示客户速查

| ID | 姓名 | 一键配仓 | 个性化 |
|----|------|----------|--------|
| C20250602001 | 张女士 | 默认演示 | 收益超预期 |
| C20250602002 | 李先生 | 保守触限 | 拒绝（健康） |
| C20250602006 | 刘女士 | 纯投资 | **复合 · 推荐** |
| C20250602008 | 孙女士 | 纯投资 | **复合 · 推荐** |
| C20250602007 | 周先生 | 纯投资 | 本金亏 |

详见 README「演示客户」与 `config/customer_profile.yaml`。

---

## 回归

```bash
pytest tests/test_allocation.py -v
pytest tests/test_flag_driven.py -v
python demo_test.py --all
```
