# H1 数据来源、许可和分发方式审计：QMSum

## 审计结论

QMSum 可以作为 1.5.2 的真实会议数据集附加实验候选，但建议采用“外部数据源引用 + 小样例派生结果”的方式，不把完整数据集直接并入仓库。

## 数据来源

| 项目 | 内容 |
|---|---|
| 数据集 | QMSum |
| 官方仓库 | https://github.com/Yale-LILY/QMSum |
| 论文 | QMSum: A New Benchmark for Query-based Multi-domain Meeting Summarization |
| 论文页 | https://arxiv.org/abs/2104.05938 |
| 数据规模 | 232 场会议，1,808 个 query-summary pair |
| 数据域 | Academic、Product、Committee |
| 数据格式 | JSON / JSONL |
| 关键字段 | topic_list、general_query_list、specific_query_list、meeting_transcripts |

## 许可审计

| 层级 | 审计结果 |
|---|---|
| QMSum 仓库 | 仓库标注 MIT License |
| AMI 来源会议 | AMI Corpus 页面说明信号、转写和部分标注公开发布在 CC BY 4.0 下 |
| ICSI 来源会议 | ICSI Meeting Corpus 也需按其页面许可要求处理 |
| Committee 来源会议 | 包含公开会议发言和真实人物姓名，需按原始公开资料属性谨慎展示 |

## 分发方式建议

采用以下方式，降低许可和仓库体积风险：

1. 仓库内只保存审计文档、样例选择清单、处理脚本、派生结果和人工金标准。
2. 不提交完整 QMSum 原始数据。
3. H2 只选择 1 个主样例和最多 2 个辅助样例。
4. 原始数据如需本地运行，由脚本从官方仓库读取或提示用户手动下载。
5. 截图和教材素材只展示必要短片段，避免大段复刻真实会议转写。

## 隐私与安全边界

- QMSum 是公开研究数据，但部分会议包含真实人物姓名、职务或公开发言。
- 附加实验不得把真实人物信息伪装成虚构数据。
- Streamlit 截图和事实包不得显示 API Key、`.env` 或与实验无关的本地文件。
- 对 Committee 类会议，优先使用公开身份发言的会议；如涉及敏感个人信息，应换样例或脱敏。

## 与主实验的关系

- 主实验 `lab02_meeting_minutes/experiment_lock.json` 保持 `accepted`。
- 附加实验不改变主实验验收结果。
- 附加实验单独维护样例、金标准、结果和事实记录。

## H2 前建议

优先从 QMSum 的 Product 或 Academic 域选择一个较短会议样例，因为它更接近产品会议纪要实验场景，也比 Committee 域更少涉及公开政治人物和议会发言。

H2 需要确认：

- 具体样例 ID；
- 是否允许本地下载该样例原文；
- 是否允许保留样例短片段或派生版输入；
- 是否需要脱敏；
- 附加实验的人工金标准字段是否继续沿用行动项、决策、未决问题三类。
