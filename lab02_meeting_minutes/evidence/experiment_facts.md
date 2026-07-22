# 实验事实记录

## 基本信息
- 实验编号：1.5.2
- 实验名称：智能会议纪要与任务提取助手
- 数据类型：中文虚构教学会议转写
- 当前阶段：H4
- 当前锁状态：accepted

## 冻结版本
| 项目 | 版本 |
|---|---|
| dataset | dataset_h2_draft_20260720 |
| gold_standard | gold_v1_h2_confirmed |
| model | deepseek-v4-flash |
| prompt | prompt_v11_open_question_precision_guard_h4_dirty |
| schema | schema_v1_h3_draft |
| validator | validator_v2_noise_tolerant_evidence |
| chunking | chunking_v1_h3_draft |
| date_normalizer | date_normalizer_v1_h3_draft |
| evidence_repair | evidence_repair_v2_qmsum_line_fallback |
| gold_compare | gold_compare_v1_h3_draft |

## 已验证事实
- H2 全量样例包含 main 1 个、demo 3 个、regression 5 个、edge 6 个。
- Mock 固定回归覆盖 15 个样例，结果为 ok=true。
- 代表真实回归覆盖 meeting_main_001、demo_002、regression_005、edge_005_discussion_no_decision，结果为 ok=true。
- 当前真实 API 调用计数为 used=37，remaining=13，limit=50。
- 用户已确认：如实际需要超过 50 次真实调用，可将上限提高到 100 次。
- Streamlit 界面已实现，覆盖输入、运行状态、结构化结果、校验结果、模型信息和结果下载。
- 已生成 6 张 Streamlit 截图：概览、上传/粘贴、结构化结果、真实数据附加实验、QMSum 完整数据集入口、文件下载页。
- H4 自动验收脚本 run_acceptance.py 已通过，结果为 ok=true。
- H4 最终人工验收已于 2026-07-20 经用户确认通过。

## 未完成事实
- 正式教材正文未编写。
