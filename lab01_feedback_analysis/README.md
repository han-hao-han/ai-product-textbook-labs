# 实验 1.5.1：基于大模型 API 的用户反馈智能分析助手

本实验使用真实中文餐饮评论和大模型 API，完成总体情感判断、评价维度识别、连续原文证据提取、问题概括与改进建议生成。项目同时提供命令行、CSV 批量处理和 Streamlit 可视化界面。

## 当前状态

- 核心功能：已完成
- 默认模型：`deepseek-v4-flash`
- Prompt 版本：`v3_billing_consistency`
- 固定演示集真实回归：`5/5`
- 最终本地验收：`FINAL_ACCEPTANCE_OK`
- GitHub 发布：公开发布包不包含 `expected_outputs/` 和截图
- 截图整理：本地保留，发布前需逐张人工脱敏确认

## 主要功能

- 调用 OpenAI-compatible 大模型 API
- 输出严格 JSON
- 使用 Pydantic 校验字段和枚举值
- 识别 `location`、`service`、`price`、`environment`、`food`
- 检查证据是否为输入评论中的连续原文
- 拒绝省略号拼接或虚构证据
- 支持单条命令行分析
- 支持 CSV 批量分析和逐条保存
- 支持 Streamlit 单条与批量界面
- 支持 Mock 测试和固定真实结果验收

## 项目结构

```text
lab01_feedback_analysis/
├─ README.md
├─ requirements.txt
├─ app.py
├─ batch.py
├─ cli.py
├─ DATA_LICENSE.md
├─ src/
│  ├─ analyzer.py
│  ├─ json_parser.py
│  ├─ prompts.py
│  ├─ schemas.py
│  ├─ semantic_checks.py
│  └─ validators.py
├─ data/
│  ├─ feedback_main_1.csv
│  ├─ feedback_demo_5.csv
│  ├─ feedback_regression_20.csv
│  └─ feedback_extension_100.csv
├─ scripts/
└─ tests/
```

说明：`expected_outputs/` 保存真实模型运行结果，截图可能包含本地配置界面；本次 GitHub 发布不上传这两类材料。

# 快速开始

在项目根目录执行：

```bat
conda activate research_env
pip install -r lab01_feedback_analysis\requirements.txt
```

配置 `.env` 后，可以先运行一条命令行测试：

```bat
python lab01_feedback_analysis\cli.py --review-id demo-001 --text "味道很好，但是服务态度很差。" --show-metadata
```

启动 Streamlit：

```bat
streamlit run lab01_feedback_analysis\app.py
```

运行固定五条真实评论的批量分析：

```bat
python lab01_feedback_analysis\batch.py --input "lab01_feedback_analysis\data\feedback_demo_5.csv" --output "lab01_feedback_analysis\results\batch\feedback_demo_5_result.csv"
```

# 环境配置

## 已验证环境

| 项目 | 版本 |
|---|---|
| 操作系统 | Windows 11 |
| Python | 3.10.20 |
| Conda 环境 | `research_env` |
| openai | 2.46.0 |
| pydantic | 2.13.4 |
| python-dotenv | 1.2.2 |
| pandas | 2.3.3 |
| streamlit | 1.59.2 |

## 安装依赖

```bat
pip install -r lab01_feedback_analysis\requirements.txt
```

`requirements.txt` 固定为：

```text
openai==2.46.0
pydantic==2.13.4
python-dotenv==1.2.2
pandas==2.3.3
streamlit==1.59.2
```

## API 配置

在仓库根目录创建 `.env`：

```env
LLM_API_KEY=你的API密钥
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-v4-flash
LLM_TEMPERATURE=0
```

安全要求：

- 不要把 API Key 写入 Python 文件
- 不要在截图中展示 API Key
- `.env` 必须加入 `.gitignore`
- 提交前执行 `git check-ignore .env`
- 不要把 `.env` 上传到 GitHub

# 命令行

查看帮助：

```bat
python lab01_feedback_analysis\cli.py --help
```

单条分析：

```bat
python lab01_feedback_analysis\cli.py --review-id 7688 --text "评论原文" --show-metadata
```

JSON 输出：

```bat
python lab01_feedback_analysis\cli.py --review-id demo-json --text "味道很好，但是服务态度很差。" --json
```

成功时会输出：

- `review_id`
- `overall_sentiment`
- 评价维度和情感
- 连续原文证据
- `issue_summary`
- `suggested_action`
- 模型名称
- Prompt 版本
- 请求耗时
- Token 使用量

命令行退出码：

- `0`：分析成功
- `1`：API、解析或校验失败
- `2`：命令行参数或输入错误

# 批量分析

输入 CSV 至少需要包含：

```text
review_id
review_text
```

运行固定演示集：

```bat
python lab01_feedback_analysis\batch.py --input "lab01_feedback_analysis\data\feedback_demo_5.csv" --output "lab01_feedback_analysis\results\batch\feedback_demo_5_result.csv"
```

限制处理数量：

```bat
python lab01_feedback_analysis\batch.py --input "lab01_feedback_analysis\data\feedback_extension_100.csv" --limit 10
```

遇到首条错误立即停止：

```bat
python lab01_feedback_analysis\batch.py --input "lab01_feedback_analysis\data\feedback_demo_5.csv" --stop-on-error
```

批量程序具有以下行为：

- 保留输入 CSV 原字段
- 每处理完一条就保存进度
- 单条失败时记录错误类型和错误信息
- 默认继续处理后续记录
- 输出总体情感、维度签名和完整维度 JSON
- 记录模型、Prompt、耗时和 Token

本实验固定五条演示集的真实结果：

```text
成功：5/5
失败：0/5
平均成功请求耗时：2.875 秒
总 Token：9852
```

该结果是一次固定实验运行记录，重新调用模型时耗时、Token 和自然语言表述可能发生变化。

# Streamlit

启动：

```bat
streamlit run lab01_feedback_analysis\app.py
```

默认地址通常为：

```text
http://localhost:8501
```

页面包含两个标签页：

## 单条分析

输入评论 ID 和评论内容后，展示：

- 总体情感
- 评价维度
- 情感标签
- 连续原文证据
- 问题概括
- 改进建议
- 模型与 Token 信息

## 批量分析

支持：

- 使用内置五条演示数据
- 上传自定义 CSV
- 指定处理条数
- 查看成功数、失败数和平均耗时
- 下载完整批量结果 CSV

点击分析按钮会调用真实 API，并可能产生费用。

# 结构化输出与证据校验

系统要求模型仅输出 JSON，并使用 Pydantic 校验：

- 字段是否完整
- 情感是否属于合法枚举
- 评价维度是否属于合法枚举
- `review_id` 是否与输入一致
- `evidence` 是否为空

业务校验进一步检查：

```python
evidence in review_text
```

因此，证据必须是评论中的连续原文。以下情况会被拒绝：

- 改写评论内容
- 总结后作为证据
- 使用 `...`、`……` 或 `…` 拼接不连续片段
- 输出评论中不存在的词语

# 默认模型

当前默认配置：

| 项目 | 值 |
|---|---|
| 平台 | DeepSeek |
| 模型 | `deepseek-v4-flash` |
| Base URL | `https://api.deepseek.com` |
| temperature | `0` |
| 思考模式 | `disabled` |
| Prompt | `v3_billing_consistency` |

选择理由：

- 固定评论上的关键维度识别较稳定
- 能够输出连续原文证据
- 对点单价格与实际收费不一致的识别较完整
- 相比已测试候选模型，速度和校验通过率更均衡

已知限制：

- 大模型输出仍具有概率性
- 自然语言概括和建议可能变化
- 当前只面向中文餐饮评论
- 当前评价维度固定为五类
- 固定五条测试不能代表所有真实评论
- API 网络和平台状态会影响运行

# 模型替换

本项目使用 OpenAI-compatible 客户端。替换模型时，至少修改 `.env` 中的：

```env
LLM_API_KEY=新平台API密钥
LLM_BASE_URL=新平台兼容地址
LLM_MODEL=精确模型名称
LLM_TEMPERATURE=0
```

替换后必须重新执行：

1. 单条 smoke test
2. 同一评论至少三次稳定性测试
3. 固定五条语义回归
4. 连续原文证据检查
5. 批量结果检查
6. 最终验收脚本

不同平台可能需要不同的 `extra_body` 参数。例如，关闭思考模式的参数结构可能不同。不要直接复制其他平台的私有参数。

本实验曾测试过 GLM 和 Qwen 候选模型：

- GLM 能识别多收费问题，但多次遗漏 `price` 维度
- Qwen 能识别价格问题，但多次使用省略号拼接不连续证据
- 因此当前版本保留 DeepSeek 为默认模型

上述结论仅适用于本实验固定数据、Prompt 和测试时间，不代表通用模型排名。

# 数据生成

## 数据集

本实验使用 ASAP 中文餐饮评论数据集。

固定上游版本：

```text
975122a60065240124df62cb4d5dbfd19ed9ef2c
```

数据许可和来源说明见：

```text
lab01_feedback_analysis/DATA_LICENSE.md
```

## 固定子集

| 文件 | 用途 | SHA256 |
|---|---|---|
| `feedback_main_1.csv` | 主示例 | `4c7b45087aadaf5b164ea8f343578b5dce1d3cbcadb9361b6acf086d169d40b7` |
| `feedback_demo_5.csv` | 教材与界面演示 | `885bf4201b6c49d21cdeb7eca349669b7a9e81474d241956e1be4ec4edfa055d` |
| `feedback_regression_20.csv` | 回归测试 | `a011b24fa02832726ff590b99c01a80f5efa5ad79fa075f143b9d7b9474e6fcb` |
| `feedback_extension_100.csv` | 扩展实验 | `ae52a8d478c893571a0b6b6d6a539466b0c63b7f9698b17b653bb11b882a3d3b` |

五条演示评论 ID：

```text
7688
13222
2828
39662
24593
```

子集生成原则：

- 使用真实数据，不编造评论
- 固定上游 Git Commit
- 固定评论 ID
- 保留原始评论文本
- 保存 SHA256
- 不使用模型生成评论作为主实验数据

重新生成数据时，应使用项目中的数据准备脚本，并再次核对文件哈希。不要手工修改固定 CSV 后仍沿用原哈希。

# 测试

## 分析器本地测试

```bat
python lab01_feedback_analysis\tests\test_analyzer_local.py
```

主要覆盖：

- 空评论 ID
- 空评论文本
- provider 参数
- 合法模型响应
- 非连续证据拒绝

## 批处理本地测试

```bat
python lab01_feedback_analysis\tests\test_batch_local.py
```

主要覆盖：

- 成功记录
- 失败记录
- 逐条保存
- 汇总统计
- 缺失列拒绝

## 本地完整验收

```bat
python lab01_feedback_analysis\scripts\final_acceptance.py
```

该脚本不会调用真实大模型 API，但会读取本地 `expected_outputs/` 中保存的真实模型运行结果。本次 GitHub 发布不上传 `expected_outputs/`，因此公开仓库用户可先运行上面的 Mock 测试；需要复核固定真实结果时，应先按本实验流程重新生成或放回本地验收结果文件。

当前已验证输出：

```text
ALL_LOCAL_TESTS_OK
REVIEW_7688_OK
REVIEW_13222_OK
REVIEW_2828_OK
REVIEW_39662_OK
REVIEW_24593_OK
BATCH_REAL_RESULTS_OK
ENV_SAFETY_OK
FINAL_ACCEPTANCE_OK
```

# 验证清单

提交前逐项确认：

- [ ] `requirements.txt` 已固定依赖版本
- [ ] `.env` 存在于本地
- [ ] `.env` 已被 `.gitignore` 忽略
- [ ] `.env` 未被 Git 跟踪
- [ ] `README.md` 启动命令与当前代码一致
- [ ] `DATA_LICENSE.md` 包含数据来源和许可
- [ ] 固定 CSV 文件哈希一致
- [ ] CLI 单条分析通过
- [ ] JSON 输出通过
- [ ] Streamlit 单条分析通过
- [ ] Streamlit 批量分析通过
- [ ] Mock 本地测试通过
- [ ] 五条真实批量结果通过
- [ ] 每条证据均为连续原文
- [ ] 最终验收输出 `FINAL_ACCEPTANCE_OK`
- [ ] 截图中不存在 API Key
- [ ] 截图中不存在账号、邮箱或个人路径
- [ ] Git 提交前已人工检查 `git diff`
- [ ] 未经明确授权不执行 GitHub Push 或 Release

# 常见问题

## 输入文件不存在

固定演示文件实际路径：

```text
lab01_feedback_analysis/data/feedback_demo_5.csv
```

不是：

```text
lab01_feedback_analysis/data/processed/feedback_demo_5.csv
```

## API Key 未生效

确认：

- `.env` 位于仓库根目录
- 环境变量名称与代码一致
- API Key 前后没有额外空格
- Base URL 与模型平台匹配

## 证据校验失败

模型可能改写或拼接了原文。应继续保留严格校验，不建议改为只判断语义相似。

## Streamlit 仍显示旧页面

停止旧进程后重新运行：

```bat
streamlit run lab01_feedback_analysis\app.py
```

# 安全说明

用户评论属于不可信输入。当前实验已限制模型输出结构，但仍应注意：

- 不把输入内容当作系统指令
- 不执行评论中的代码或命令
- 不在日志中打印 API Key
- 不把敏感评论上传到不被允许的平台
- 不将 `.env`、本地账号或个人路径提交到仓库

# 交付状态

当前阶段：

- README：已补齐
- 固定依赖：已补齐
- DATA_LICENSE：已存在并通过内容检查
- 截图：暂时忽略，仍为待完成项
- Commit：未创建
- Push：未执行
- Release：未创建

任何 GitHub 写操作都必须先获得用户明确同意。
