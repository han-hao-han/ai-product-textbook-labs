# 工程交接摘要

## 当前状态

H0～H4和四个读者体验检查点均已由用户确认。最终Streamlit、正式评价、Codex
盲审、公开示例、自动测试、已知限制和Git边界均已完成工程验收。正式教材正文仍
待人工编写。

## 冻结基线

```text
FastAPI Release: 0.136.3
FastAPI Commit: 82064857539e6286522c347b4b11331b48dd2378
中文文档: 102
Chunk: 400
语料SHA-256: 71cf57bca05ddbc43a61a6155690f5bd4ebc07cc1cf6f181fe80bfc2d66e741d
Embedding: Qwen/Qwen3-Embedding-0.6B
Embedding Revision: 97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3
向量维度: 1024
索引SHA-256: 250ddaea4e54c67d0de36af64afe66667794d3c0100ecf73706e1ad115262909
门控阈值: 0.6831968426704407
生成模型: qwen3.7-plus-2026-05-26
Codex CLI: 0.145.0
Judge模型: gpt-5.6-sol
Judge reasoning effort: medium
```

## 模块职责

- `scripts/`是读者可运行的薄入口。
- `src/`保存下载、清洗、Chunk、Embedding、检索、门控、生成、校验、评价、
  Judge和示例导出的共享逻辑。
- `configs/`与`prompts/`保存冻结配置和Prompt。
- `app.py`只加载现有运行产物，不自动下载、建库或修复。
- `results/runs/`保存本地完整历史，默认不提交。
- `results/example_candidates/`保存本地候选，默认不提交。
- `results/checkpoints/examples/`保存已由用户确认的有限公开示例。

## 推荐运行顺序

各检查点必须分开运行并在人工查看后继续：

```powershell
python scripts/init_experiment_run.py
python scripts/download_fastapi_docs.py --experiment-run-id <id>
python scripts/inspect_documents.py --experiment-run-id <id>
python scripts/build_corpus.py --experiment-run-id <id>
python scripts/prepare_embedding_model.py --experiment-run-id <id>
python scripts/build_index.py --experiment-run-id <id>
python scripts/demo_retrieval.py --experiment-run-id <id>
python scripts/audit_h2_question_sets.py --experiment-run-id <id>
python scripts/build_h2_candidate_review.py --experiment-run-id <id>
python scripts/calibrate_threshold.py --experiment-run-id <id>
python scripts/prepare_generation_client.py --experiment-run-id <id>
streamlit run app.py
python scripts/run_evaluation.py --experiment-run-id <id>
python scripts/prepare_judge_inputs.py --experiment-run-id <id>
python scripts/run_codex_judge.py --experiment-run-id <id>
python scripts/build_evaluation_report.py --experiment-run-id <id>
python scripts/build_example_candidates.py --experiment-run-id <id>
```

公开示例候选经人工确认后，才运行：

```powershell
python scripts/export_checkpoint_examples.py --experiment-run-id <id>
```

目标目录已存在时导出会失败，不提供覆盖参数。

## 本地真实运行

本轮完整运行ID：

```text
fastapi_rag_20260728_005918_31df34
```

四个检查点报告均已生成。30道正式题全部形成首次持久化终态；15个有效回答全部
完成一次Codex盲审，没有Judge失败、校验失败或工具污染。检查点4的`warning`
保留2个连接失败和1个回答校验失败。

## 凭据与提交边界

- `.env`、API Key、Authorization Header、模型权重、完整语料、完整运行记录和
  Judge stdout/stderr不得提交。
- 公开示例导出会扫描凭据模式和本地绝对路径，只导出同一运行链的四组检查点材料。
- 创建Commit、Push、Tag和Release均需要用户单独确认。

## 验收与后续

- 自动测试必须使用Python 3.10正式环境；Base Python不包含完整运行依赖。
- Streamlit现场验收应确认三个Tab、主动运行、阶段状态、引用、逐题正式结果、
  下载按钮和无意外重复调用。
- 已知限制见`KNOWN_LIMITATIONS.md`。
- 当前统一状态表述为：

```text
实验工程与读者体验流程完成，正式教材正文待人工编写
```
