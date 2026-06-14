# 智能资配

**人人都是专业财富顾问**

基于四笔钱框架的配置驱动智能投顾系统，面向理财经理提供卡片化资产检视、一键智能配仓、方案解读与投后陪伴能力。业务规则集中在 YAML 配置中，支持后台可视化维护资产配置模型与风险映射。

## 核心特性

- **双层配置驱动**：战略层（风险画像 → 模型指派 → 四笔钱目标区间）与战术层（产品匹配、产品约束、求解策略）
- **多种配仓模式**：智能一键配仓 + 单类聚焦+ 人工微调配仓，兼顾效率与专业裁量，科学配置，以四笔钱为配置骨架，卡片化呈现占比、区间偏离与健康度，让复杂配置一目了然。
- **智能配仓引擎**：在大类—产品双层架构上完成存量优先、区间约束、二次分配与合规限额下的自动化调仓决策，同时灵活支持单产品占比限制，闲置资金是否追加、最低可优化资产门槛等全账户优化约束，满足多样化资产配置场景
- **动态求解算法**：支持区间内「最小资金异动」、越界动态回退、类内优先级集中调仓与限额溢出再分配，在模型合规与客户体验间智能寻优，规则热更新、引擎零侵入
- **实时联动校准**：卡片要素全部实时联动，支持全账户一键、单类聚焦与人工微调的实时联动重算，方案随编辑即时校准
- **AI 增强顾问**：LUI模式生成资产健康度诊断，配置解读与沟通话术；可选大模型顾问副驾驶，基于实时资产与方案上下文提供问答式专业辅助，固化规则进行兜底
- **事件驱动个性化陪伴**（待建设）：基于市场异动、回撤阈值、持仓偏离与客户生命周期事件自动触发再平衡建议，并推送差异化投后陪伴与沟通策略
- **全生命周期资产配置**：覆盖「资产检视 → 智能配仓  → 投后陪伴」完整闭环，一站贯通客户资产配置全旅程

## 页面与入口

启动后访问 **[http://localhost:8000](http://localhost:8000)**，默认进入智能资配页。


| 页面   | 路径                              | 说明                       |
| ---- | ------------------------------- | ------------------------ |
| 智能资配 | `/smart_allocation.html`        | 主工作台：检视 + 配仓 + AI 顾问     |
| 客户资产 | `/index.html`                   | 四笔钱资产概览卡片                |
| 配置方案 | `/result.html`                  | 配仓结果与解读详情                |
| 投后陪伴 | `/aftercare.html`               | 回访周期、回撤预警、沟通话术           |
| 模型建立 | `/admin/model_config.html`      | 维护 P1–P5 模型及五类资产下限/基准/上限 |
| 模型指派 | `/admin/portfolio_mapping.html` | 客户风险等级与资产配置模型映射          |


导航栏左侧为业务页签，右侧为「模型建立 / 模型指派」配置入口。

## 目录结构

```
weathmanage/
├── config/                    # 业务规则（YAML）
│   ├── model_config.yaml      # 资产配置模型（五类资产阈值）
│   ├── portfolio_mapping.yaml # 风险等级 → 模型映射
│   ├── four_money_mapping.yaml# 资产类型 → 四笔钱聚合规则
│   ├── product_constraint.yaml# 底层产品与调仓优先级
│   ├── customer_profile.yaml  # 演示客户画像
│   ├── four_money_rule.yaml   # 求解器与展示规则
│   ├── four_money_page.yaml   # 前台卡片与权限
│   ├── aftercare_rule.yaml    # 投后陪伴规则
│   └── llm_config.yaml        # 大模型对话配置
├── asset_allocation/          # 智能配仓引擎
├── agent_core/                # AI 解读与顾问对话
├── core/                      # 服务层、配置加载与写入
├── api/                       # FastAPI 路由
├── frontend/                  # 业务前台 + admin 配置后台
├── tests/                     # 单元与接口测试
├── docs/API.md                # 接口文档
├── demo_test.py               # 端到端自测脚本
└── main.py                    # 应用入口
```

## 快速启动

```bash
cd weathmanage
python3 -m venv .venv
source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

服务默认监听 `http://127.0.0.1:8000`。

### 可选：启用 AI 顾问对话

```bash
cp .env.example .env
# 编辑 .env，填入 LLM_API_KEY（OpenAI 兼容接口）
```

未配置 Key 时，配仓与规则解读仍可用；顾问浮窗会提示未启用大模型。

## 配置链路

```
客户风险等级 (customer_profile)
    ↓
投资组合偏好 / 可承受亏损 (portfolio_mapping)
    ↓
资产配置模型 P1–P5 (model_config)
    ↓
五类资产阈值 [下限, 基准, 上限]
    ↓
四笔钱阈值聚合 (four_money_mapping，生钱的钱 = 权益 + 另类)
    ↓
智能配仓引擎 (auto_rebalance_engine)
```

**模型保存校验**：编辑模型时，四笔钱基准值之和须等于 100%（容差 0.01%）。

**投资模型说明**：当前演示模型为保障类基准 0% 的纯投资模型。若客户持有重疾险/意外险，配仓可能建议减配保障类产品；可选用下方「纯投资客户」演示。

## 演示客户

共 8 名演示客户，覆盖五档风险画像（`投资规划` 品类）。


| ID           | 姓名  | 风险画像 | 备注          |
| ------------ | --- | ---- | ----------- |
| C20250602001 | 张女士 | 平衡型  | 含保障类持仓      |
| C20250602002 | 李先生 | 保守型  | 含保障类持仓      |
| C20250602003 | 王先生 | 进取型  | 含保障类持仓      |
| C20250602004 | 赵女士 | 稳健型  | 含保障类持仓      |
| C20250602005 | 陈先生 | 成长型  | 含保障类持仓      |
| C20250602006 | 刘女士 | 平衡型  | **纯投资**，无保单；演示 **收益超预期 + 本金损失超阈值** |
| C20250602007 | 周先生 | 稳健型  | **纯投资**，无保单 |
| C20250602008 | 孙女士 | 成长型  | **纯投资**，无保单；演示 **收益超预期 + 波动率超预期** |


- 客户画像：`config/customer_profile.yaml`
- 持仓数据：`core/data_store.py`（`DEMO_HOLDINGS`）

推荐演示：
- **刘女士 `C20250602006`**：平衡型纯投资，财富健康标志 **收益超预期 + 本金损失超阈值**（标志驱动资配优先止损）。
- **孙女士 `C20250602008`**：成长型纯投资，财富健康标志 **收益超预期 + 波动率超预期**（权益已收到基准止盈，兼降波动）。

## 一键自测

```bash
python demo_test.py                          # 默认客户 C20250602001
python demo_test.py --customer C20250602006  # 纯投资客户
python demo_test.py --all                    # 全部演示客户
python demo_test.py --json                   # JSON 输出

pytest tests/ -v                             # 全量测试
pytest tests/test_model_config.py -v         # 模型配置与映射
pytest tests/test_allocation.py -v           # 配仓引擎
```

## 主要 API


| 方法       | 路径                               | 说明              |
| -------- | -------------------------------- | --------------- |
| GET      | `/api/customer/list`             | 演示客户列表          |
| GET      | `/api/asset/overview`            | 客户资产概览（四笔钱卡片）   |
| POST     | `/api/allocation/auto_rebalance` | 一键智能配仓          |
| POST     | `/api/allocation/manual_adjust`  | 人工微调重算          |
| GET      | `/api/allocation/resolve`        | 风险 → 模型 → 四笔钱阈值 |
| GET      | `/api/model/list`                | 模型列表（含五类资产阈值）   |
| GET/POST | `/api/model/*`                   | 模型详情、保存、删除      |
| GET/POST | `/api/portfolio/map`             | 风险映射查询与保存       |
| GET      | `/api/ai/status`                 | 大模型是否可用         |
| POST     | `/api/ai/chat`                   | 智能投顾顾问对话        |
| POST     | `/api/aftercare/build_plan`      | 投后陪伴方案          |


完整说明见 [docs/API.md](docs/API.md)。

## 技术栈

- **后端**：Python 3.8+、FastAPI、PyYAML、Pydantic
- **前端**：原生 HTML / CSS / JavaScript（无构建步骤）
- **AI**：OpenAI 兼容 HTTP API（通义、DeepSeek 等均可）

## 配置修改指引


| 需求        | 修改文件                                           |
| --------- | ---------------------------------------------- |
| 新增演示客户    | `customer_profile.yaml` + `core/data_store.py` |
| 调整模型阈值    | 后台「模型建立」或 `model_config.yaml`                  |
| 调整风险映射    | 后台「模型指派」或 `portfolio_mapping.yaml`             |
| 新增/调整产品   | `product_constraint.yaml`                      |
| 四笔钱聚合规则   | `four_money_mapping.yaml`                      |
| 卡片文案与按钮权限 | `four_money_page.yaml`                         |
| 大模型参数     | `llm_config.yaml` + `.env`                     |


修改 YAML 后重启服务即可生效；通过后台保存的模型与映射会写回对应配置文件。