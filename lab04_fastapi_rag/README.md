# 1.5.4 基于RAG的FastAPI中文文档问答助手

当前状态：

```text
检查点1已由读者确认通过
检查点2已由读者确认通过
H2题集与H3检索门控阈值已冻结
检查点3已由读者确认通过
检查点4已由读者确认通过
H4最终工程与读者体验验收已通过
```

本实验使用FastAPI官方仓库固定版本的中文学习文档，帮助读者观察：

```text
固定Commit
→ 中文文档筛选
→ 冻结代码依赖展开
→ Markdown清洗
→ 可追溯Chunk
→ 固定Revision的本地Embedding
→ NumPy精确余弦Top 5
→ 冻结校准集上的检索门控阈值
→ Top 1门控
→ Top-k证据结构化回答、引用校验或拒答
→ 程序评价检索、分类与拒答机制
→ Codex CLI独立盲审回答语义
```

正式评价只允许使用冻结题集的`attempt_001`。百炼客户端是否可在线调用，以当前
运行目录`generation/current_state.json`中的实际准备结果为准。

## 冻结来源

```text
Repository: https://github.com/fastapi/fastapi
Release: 0.136.3
Commit: 82064857539e6286522c347b4b11331b48dd2378
License: MIT
```

范围：

- `tutorial`：50页；
- `advanced`：34页；
- `deployment`：7页；
- `how-to`：11页；
- 合计：102页。

以下3页按H1结论排除：

- `docs/zh/docs/deployment/fastapicloud.md`；
- `docs/zh/docs/deployment/cloud.md`；
- `docs/zh/docs/how-to/testing-database.md`。

代码依赖边界：

- 默认只允许展开仓库根目录下的 `docs_src/**`；
- 唯一例外是
  `docs/zh/docs/how-to/configure-swagger-ui.md`
  对 `fastapi/openapi/docs.py` 的 `ln[9:24]` 引用；
- 该例外必须出现且只能出现一次；
- 其他 `fastapi/**` 引用仍会被审计程序拒绝。

此例外来自固定Commit中文页面的真实引用，用于展示Swagger UI默认配置，
仍受同一FastAPI仓库MIT许可证约束。

完整官方ZIP、解压文档、清洗语料、Chunk和运行报告仅保存在本地，不提交仓库。

## 运行环境

正式读者基线为Python 3.10.x和Conda。检查点1核心实现只使用Python标准库；
检查点2使用以下H3冻结依赖：

```text
torch 2.11.0
numpy 1.23.5
transformers 4.57.6
huggingface-hub 0.36.2
tokenizers 0.22.1
safetensors 0.7.0
```

安装命令：

```powershell
python -m pip install -r requirements.txt
```

自动测试另需`requirements-dev.txt`中的`pytest`。

## 检查点1命令

请在本目录运行：

```powershell
python scripts/init_experiment_run.py
```

记录命令输出中的`experiment_run_id`，依次运行：

```powershell
python scripts/download_fastapi_docs.py --experiment-run-id <id>
python scripts/inspect_documents.py --experiment-run-id <id>
python scripts/build_corpus.py --experiment-run-id <id>
```

最后查看：

```text
results/runs/<id>/checkpoints/checkpoint_1/report.md
```

检查点1不会调用任何模型。

## Chunk规则

- 冻结策略：`heading_aware_adjacent_merge_v1`；
- 目标长度为500～800估算Token；
- 同一页面内具有共同父标题的相邻短小节可以合并；
- Chunk正文会保留所覆盖的必要标题；
- `section_paths`记录Chunk覆盖的全部章节路径；
- 不跨页面合并；
- 只有同一章节内部切分时才加入80～120估算Token的Overlap；
- 代码块和表格保持完整，不为满足长度上限而切断；
- 短页面、文档尾部、加入下一块会超过800以及超长原子代码块，
  都会在Chunk及报告中记录例外原因。

## Token计数说明

Chunk在检查点1构建时尚未调用Embedding模型，因此长度规划使用：

```text
deterministic_cjk_ascii_estimate_v1
```

它是透明、确定、无第三方依赖的估算方法，不等同于Qwen tokenizer的真实Token数。
检查点2会在真正送入模型前使用Qwen tokenizer复核实际输入长度；超过冻结的8192
Token时阻断，不静默截断。

## 检查点2冻结方案

```text
Model: Qwen/Qwen3-Embedding-0.6B
Revision: 97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3
License: Apache-2.0
Device: CPU（当前运行已在初始化阶段冻结）
Dimension: 1024
Inference / storage dtype: float32
Padding: left
Pooling: last non-padding token
Normalization: L2
Document instruction: none
Query max_length: 8192
Top-k: 5
```

文档直接Embedding，不添加任务指令。查询格式固定为：

```text
Instruct: Given a Chinese question about FastAPI, retrieve relevant passages from the FastAPI Chinese documentation that answer the question.
Query:{query}
```

使用Transformers直接加载，不引入`sentence-transformers`。模型只在准备步骤按固定
Revision下载到Hugging Face共享缓存；索引和检索步骤只读本地缓存，不会自动联网补全。
模型权重、索引和检查点报告只保存在本地运行目录或共享缓存，不提交仓库。

准备步骤会保留Hugging Face的`.incomplete`断点文件。只有连接中断、读取超时等
可恢复网络错误会进行最多3次有限重试并复用断点；认证错误、Revision错误、文件大小
或哈希不匹配不会重试。`hf_xet`未安装时会回退到普通HTTP，性能提示不代表失败。

## 检查点2命令

检查点1通过后，沿用同一个`experiment_run_id`，依次单独运行：

```powershell
python scripts/prepare_embedding_model.py --experiment-run-id <id>
python scripts/build_index.py --experiment-run-id <id>
python scripts/demo_retrieval.py --experiment-run-id <id>
```

第三个命令固定查询：

```text
如何使用Pydantic模型声明请求体？
```

最后查看：

```text
results/runs/<id>/checkpoints/checkpoint_2/report.md
```

报告保留完整Top 5正文、来源、章节、Chunk ID和相似度。相似度由已L2归一化的
查询与文档向量点积得到，因此等于余弦相似度。Top 5使用NumPy全量精确排序，
不使用FAISS、向量数据库、Reranker、查询改写或生成模型。

## H2题集与门控阈值

检查点2人工确认后，先审计H2候选：

```powershell
python scripts/audit_h2_question_sets.py --experiment-run-id <id>
python scripts/build_h2_candidate_review.py --experiment-run-id <id>
```

候选结构固定为：

```text
校准集：20道知识库内 + 10道边界 + 20道知识库外
正式集：18道知识库内 + 6道边界 + 6道知识库外
```

正式库内题严格包含tutorial 9、advanced 4、deployment 3、how-to 2；
题型严格包含4道概念、5道步骤、5道代码和4道综合题，其中5题要求短Python代码。
每题预先记录必答点、可选点、关键错误和可接受来源。

候选阶段不运行Embedding，也不读取任何检索分数。人工确认后才冻结题集哈希并用
50道校准题计算Top 1分数。阈值算法要求知识库内召回率至少90%，在满足约束的
候选阈值中最大化边界与知识库外拒绝率；30道正式题在阈值冻结前不可运行或查看
分数，正式结果不得用于回调阈值。

H2确认后执行：

```powershell
python scripts/calibrate_threshold.py --experiment-run-id <id>
```

该命令先核验校准集、正式集与门控策略的冻结SHA-256，但只加载并编码50道校准题。
它会生成全部候选阈值指标、逐题Top 1结果、正式阈值候选和报告到：

```text
results/runs/<id>/calibration/threshold_v1/
```

状态为`computed_pending_h3_confirmation`时必须停下；人工确认阈值前不得运行30道
正式题，也不得根据正式题结果重新调整阈值。

正式门控阈值已由人工确认并冻结为：

```text
0.6831968426704407
```

H3-Generation已确认采用阿里云百炼
`qwen3.7-plus-2026-05-26`、OpenAI-compatible Chat Completions和
JSON Mode。按动态长度方案A，结构化输出请求不设置输出Token上限，以降低JSON
被截断的风险；分类结果仍决定Prompt要求的回答详略。

## 检查点3：完整RAG问答

先准备生成客户端：

```powershell
python scripts/prepare_generation_client.py --experiment-run-id <id>
```

凭据从当前进程的`DASHSCOPE_API_KEY`读取；若当前进程没有该变量，再精确读取
`lab04_fastapi_rag/.env`，不会搜索父目录或读取其他实验的`.env`。进程环境变量
优先，不会被文件覆盖。

首次使用可以在`lab04_fastapi_rag/`中执行：

```powershell
Copy-Item .env.example .env
```

然后只在本地`.env`中填写：

```dotenv
DASHSCOPE_API_KEY=你的百炼API_KEY
```

`.env`已由当前实验自己的`.gitignore`排除。没有凭据时命令不联网，生成状态为
`retrieval_only`；补充凭据后重新执行会创建新的`attempt_XXX`，不会覆盖历史记录。
真实准备会分别测试问题分类和回答JSON Mode，并验证Pydantic Schema。

然后启动界面：

```powershell
streamlit run app.py
```

三个Tab分别展示文档与索引、问答与检索过程、正式验证结果。问答过程严格区分：

```text
retrieval_rejected
model_refused
answered
generation_failed
validation_failed
retrieval_only
```

建议至少现场测试：

```text
知识库内：如何使用Pydantic模型声明请求体？
边界：我的8核16GB服务器在每秒5000请求时应该精确启动多少个Uvicorn worker？
知识库外：明天北京天气如何？
```

普通问答只保留在当前Streamlit会话最近10条中。需要持久化时，必须在页面中选择
体验类型、勾选确认并显式保存。知识库内、边界和知识库外各保存一条后，页面才能
生成`checkpoints/checkpoint_3/report.md`和`report.json`。

Prompt和证据使用XML式边界并转义不可信内容。在线模型看不到相似度、排名或阈值；
回答引用、Markdown安全和Python语法均由程序检查。Python代码只解析、不执行。

## 检查点4：正式评价与Codex独立盲审

H3-Judge冻结为：

```text
Codex CLI: 0.145.0
Package: @openai/codex@0.145.0
Login: ChatGPT
Model: gpt-5.6-sol
Reasoning effort: medium
Sandbox: read-only
Approval policy: never
Process policy: one question per ephemeral process, serial, no retry
```

正式评价依次执行：

```powershell
python scripts/run_evaluation.py --experiment-run-id <id>
python scripts/prepare_judge_inputs.py --experiment-run-id <id>
python scripts/run_codex_judge.py --experiment-run-id <id>
python scripts/build_evaluation_report.py --experiment-run-id <id>
```

第一步固定运行30题，并分别保存模型原始响应、解析结果、程序比较和失败记录。
正式题不会因连接、生成或校验失败而自动重跑。程序只计算检索、分类和拒答机制，
不判断回答语义。

第二步只把具有有效回答的知识库内题转换为盲审输入；生成模型、分类结果、检索
分数、门控阈值和未引用的Top 5不会发送给Judge。第三步使用冻结的Codex CLI配置，
每题启动一个只读、临时、禁止批准的独立进程，任何工具事件都标记为污染，失败
不会自动重试。第四步以全部18道知识库内题作为回答率分母，因此无有效答案或
Judge失败不会被排除出统计。

最终查看：

```text
results/runs/<id>/checkpoints/checkpoint_4/report.md
results/runs/<id>/checkpoints/checkpoint_4/report.json
```

报告状态为`warning`不等于流程失败；应结合逐题终态判断是正式生成失败、程序校验
失败、Judge失败，还是确有不正确回答。检查点4到达后必须人工查看首次运行记录，
不得通过重跑正式题或调阈值改写结果。

## H4：示例候选与最终工程验收

四个检查点确认后，先生成本地候选：

```powershell
python scripts/build_example_candidates.py --experiment-run-id <id>
```

候选保存在`results/example_candidates/<id>/`并由`.gitignore`排除。程序会核验
四组检查点来自同一运行、状态可导出、报告哈希未变化，并从正式Judge
`attempt_001`中按实际出现的回答等级选择最多3个候选。此步骤不会创建仓库公开
示例。

人工查看并确认候选后，才运行：

```powershell
python scripts/export_checkpoint_examples.py --experiment-run-id <id>
```

统一导出到`results/checkpoints/examples/checkpoint_1～checkpoint_4`。导出会再次
核验候选与报告哈希，扫描API Key、Authorization Header和本地绝对路径；目标目录
已存在时整体失败，不提供覆盖参数。完整`results/runs/`和Judge日志不会导出。

当前两个Judge公开示例已由用户确认并导出。模型输出、网络状态和耗时可能波动；
公开示例只代表一次冻结运行，不是模型的固定输出或普遍性能结论。

最终已知限制和工程接续信息分别见：

- `KNOWN_LIMITATIONS.md`
- `HANDOFF.md`
- `H4_ACCEPTANCE.md`

## 许可证

FastAPI源代码和相关文档使用MIT许可证；Qwen3-Embedding模型使用
Apache-2.0许可证。详细来源、版权与许可边界见：

```text
THIRD_PARTY_NOTICES.md
```
