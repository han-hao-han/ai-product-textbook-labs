# 附加实验交接摘要

## 核心输入

- 审计样例转换脚本：`scripts/fetch_qmsum_case.py`
- 完整数据集本地缓存工具：`scripts/qmsum_local_dataset.py`
- Streamlit QMSum 真实调用链路：`scripts/qmsum_pipeline.py`
- 仓库内转换输入：`data/selected_cases/TS3010a.md`、`data/selected_cases/IS1003a.md`、`data/selected_cases/ES2011a.md`
- 样例清单：`data/manifests/TS3010a_manifest.json`、`data/manifests/IS1003a_manifest.json`、`data/manifests/ES2011a_manifest.json`
- 人工金标准：`data/gold/TS3010a_gold.json`

## 核心运行

- 真实 Smoke Test：`scripts/run_qmsum_smoke.py --prompt v2`
- 证据修复：`scripts/repair_qmsum_smoke_output.py --prompt v2`
- 金标准对照：`scripts/compare_qmsum_gold.py --prompt v2`
- 自动验收：`run_acceptance_addon.py`
- Streamlit：可选择仓库内三样例；也可由用户下载完整 QMSum 到本地缓存后选择任意样例分析。

## 已验证结果

- v2 结构校验：通过；
- v2 evidence 校验：修复后 0 问题；
- v2 金标准语义对照：8/8 召回；
- 行动项：0；
- 未决问题：0；
- 当前 API 调用计数：37/50。
- 当前 Streamlit/QMSum 探索调用 Prompt：`addon_prompt_qmsum_real_meeting_v4_owner_decision_precision`。

## 当前状态

- H0/H1/H2/H3 已确认。
- H4 自动验收已通过，报告为 `outputs/addon_acceptance_report.json`。
- H4 人工验收尚未确认。
- 主实验 1.5.2 的 `accepted` 状态未改变。
- 完整 QMSum 数据集不提交仓库，缓存目录为 `data/downloads/qmsum_full/`。
- TS3010a 的 8/8 gold 对照结果来自历史 v2 Prompt；v4 是后续完整数据集探索用的通用 Prompt。
