# 1.5.6 基于真实零售数据的经营分析 Agent

本实验让读者观察一条受约束的工具调用链：

```text
自然语言经营问题
→ DeepSeek V4 Flash 选择七个白名单工具之一
→ Pydantic 校验工具名与参数
→ Pandas 按冻结口径计算
→ 程序生成 FACT 与图表
→ 模型组织报告
→ 程序校验报告中的数值和证据引用
```

模型不负责计算销售额、排名、占比或增长率。没有 API Key 时，页面只开放明确标记的“工具层体验”，不会用关键词路由或 Mock 冒充 Agent。

## 数据与隐私

唯一数据源是 [UCI Online Retail（ID 352）](https://archive.ics.uci.edu/dataset/352/online+retail)，许可为 CC BY 4.0。仓库不分发原始工作簿，只提供官方下载和审计脚本。

```powershell
conda activate research_env
cd lab06_retail_analysis_agent
python scripts\download_online_retail.py
python scripts\inspect_online_retail.py
```

原始工作簿应位于 `data/raw/Online Retail.xlsx`，SHA-256 必须为：

```text
43465a06f2ccf7c8b5bd2892bc7defb52f97487934fe93b16ae4c3936424676d
```

原始 `CustomerID` 只在本地用于确定性聚合；页面、运行记录和导出不得展示客户标识明细。

## 环境

当前冻结验证环境为 Python 3.10.20。已有 `research_env` 时：

```powershell
conda activate research_env
pip install -r requirements.txt
```

将 `LLM_API_KEY` 放在仓库根目录 `.env`，或在启动 Streamlit 的终端中设置。页面只显示“模型服务已配置/未配置”，不会显示密钥字符。

## 首次准备与启动

Excel 首次解析可能需要 1–2 分钟。建议先生成本地运行缓存：

```powershell
conda activate research_env
cd lab06_retail_analysis_agent
python scripts\prepare_streamlit_data.py
streamlit run app.py
```

缓存位于被 `.gitignore` 排除的 `data/cache/`。缓存包含本地客户标识，不得上传或分发；程序每次复用前会核对工作簿哈希、口径版本和行数。

## Streamlit 读者体验

页面包含四个区域：

1. **对话分析**：在线模式像普通聊天产品一样自由输入问题；离线模式手动选择一个白名单工具。
2. **数据与口径**：查看原始记录、正常销售、异常记录、时间范围、GBP 单位和冻结指标定义。
3. **教学验收**：独立运行 Q01–Q10；必须先运行某题，之后才解锁该题的人工标注参考结果与人工检查清单。
4. **运行记录**：显式下载 ZIP，或导入已有 `run_record.json` 只读查看。

聊天运行时与固定问题 Harness 相互独立：聊天框接收当前固定数据集范围内的任意自然语言经营问题，模型自主选择白名单工具；Q01–Q10 只负责确定性教学验收，不参与聊天路由。产品聊天的每次用户问题最多执行 8 次工具调用、使用 12 个真实模型响应，自动重试为 0；新问题会重新获得完整额度，整个 Streamlit 会话不累计工具次数。固定 Harness 仍使用原四次工具上限。页面刷新、切换标签、展开证据和下载均不会调用模型。

主回答采用独立的用户呈现层：程序从已经通过 Schema 校验的工具结果中提取直接结论、中文指标名称和表格，因此不会把 `{}`、`FACT-*`、`REQUEST-*` 或 `POLICY-*` 当作用户答案。V3.1 内部受控报告仍完整保留在折叠的分析依据中，用于追溯和教学验收。

如果 DeepSeek 在一次响应中同时返回多个工具调用，通用聊天适配层只采纳第一个尚未执行的合法调用；得到真实工具结果和 FACT 后，再让模型重新规划下一步。它不会预先执行模型批量列出的无关工具，也不会重复执行相同工具与参数。固定 Harness 仍维持“单次响应最多一个工具调用、单题最多四次”的根规则；产品聊天不会绕过白名单、参数校验或单次回答八次工具上限。

如果问题信息不足，Agent 会先提出一次集中澄清。用户在同一聊天框输入补充说明后，程序会用原问题、澄清回答和同一个 `turn_id` 继续该轮分析，而不是创建一个无关的新问题。聊天框允许补充文字条件，不允许上传或替换冻结的 UCI 数据集。自由问题是产品体验入口；当前有确定性参考答案的正式兼容性范围仍是 H2 冻结的 Q01–Q10。

## H4 建议操作顺序

1. 在“数据与口径”确认 541,909 条原始记录、524,878 条正常销售记录、11,763 条异常或非销售记录，以及 2011-12 不完整期间。
2. 在“对话分析”自行输入“按销售额列出前 5 个商品”，观察模型选择 `rank_products`，并查看 Schema 后参数、FACT、Top N 图表和正式报告校验。
3. 输入“完整月份中销售额最高的是哪个月，并列出该月销售额前 3 的商品”，观察模型先调用 `analyze_time_trend`，再把工具结果中的月份传给 `rank_products`；模型不得自行计算月份或排名。
4. 输入类似 Q08 的模糊问题，确认 Agent 先集中澄清；直接在同一聊天框补充时间、指标和比较对象，确认原轮次继续并产生分析结果。
5. 在“教学验收”运行 Q09、Q10，确认正确拒答并提供实验支持范围内的替代分析。
6. 在“教学验收”完成 Q01–Q10，逐题展开参考结果和人工清单，不计算综合“智能分数”。
7. 下载证据包，再在“运行记录”导入其中的 `run_record.json`，确认导入不会触发模型调用。

适合教材截图的位置是 Q06 的“工具调用 → FACT → 图表 → 报告校验”连续区域。截图前应隐藏浏览器地址、终端、`.env` 和本地运行目录；页面本身不会显示 API Key 或原始 CustomerID。

## 测试

```powershell
conda activate research_env
cd lab06_retail_analysis_agent
python -m pytest -q
```

单独检查 H4 服务和页面首屏：

```powershell
python -m pytest tests\test_h4_streamlit_service.py tests\test_h4_streamlit_app.py -q
```

自动测试只能证明代码、Schema、Mock、保存和界面首屏工作，不能替代人工体验。本实验 H4 已在用户完成现场反馈并确认“单次回答有上限、整个会话不累计”边界后通过。

## 主要文件

- `app.py`：Streamlit 薄入口，只负责交互和展示。
- `src/h4_streamlit_service.py`：真实数据加载、聊天续接、工具层体验、V3.1 Agent 接线、证据保存、会话记录和导出。
- `src/chat_runtime_v1.py`：与固定题号解耦的通用原生工具聊天运行时及响应上限。
- `src/user_answer_presenter.py`：把已验证工具结果转换成不含内部证据编号的用户答案。
- `src/tool_registry.py` / `src/retail_tools.py`：七个白名单工具与 Pandas 确定性计算。
- `src/fact_builder.py` / `src/chart_data.py`：FACT 和图表数据构造。
- `src/online_native_tool_candidate_claim_controller_v3_1.py`：最终冻结的 V3.1 在线 Agent 与报告控制器。
- `src/fixed_question_validation.py`：Q01–Q10 确定性验收 Harness。
- `scripts/prepare_streamlit_data.py`：生成不分发的本地运行缓存。
- `config/h2_metric_contract.json`：冻结清洗与指标口径。
- `config/h2_validation_questions.json`：十道固定问题、参考结果和人工检查清单。

## 已知限制

- 内部报告措辞仍采用受控 V3.1 架构，安全但较机械；它默认折叠，不再作为主回答。
- 解释与建议使用冻结模板，不支持因果诊断或预测。
- 多轮只保存当前 Streamlit 会话；文本条件可以继承，但历史 FACT 不进入新报告，跨轮问题必须重新调用工具。
- 自由问题仍受七个工具和固定数据范围约束；没有成本、库存或未来观测的问题会被拒答。
- H4 已于 2026-08-05 经用户现场体验和边界确认通过；后续改动若影响工具、Prompt、报告或聊天限额，需要重新执行相应回归与人工抽查。
