# 附加实验事实记录

## 基本信息

- 实验编号：1.5.2-addon-real-meeting-dataset
- 父实验：1.5.2
- 数据集：QMSum
- 主样例：Product/val/TS3010a
- 仓库内保留样例：TS3010a、IS1003a、ES2011a
- 数据类型：真实公开研究会议数据集的小规模转换输入
- 当前状态：H4 人工验收候选

## 已验证事实

- H0 已确认：附加实验不改变主实验 `accepted` 状态。
- H1 已确认：QMSum 作为数据候选，采用不提交完整原始数据集的分发方式。
- H2 已确认：选择 TS3010a 作为主案例，并确认小规模人工金标准草案。
- H3 已确认：复用主实验 Schema、Pipeline、证据校验、日期规范化和金标准对照，并使用 QMSum 附加 Prompt。
- 仓库只保留三个经过审计的转换样例：`TS3010a.md`、`IS1003a.md`、`ES2011a.md`。
- 完整 QMSum 数据集不提交仓库；用户可在 Streamlit 中自行下载到本地忽略目录 `data/downloads/qmsum_full/`。
- 第 1 次真实 Smoke Test 使用 TS3010a 和 v1 Prompt，API 计数从 28 增至 29，金标准召回 3/8。
- 第 2 次真实 Smoke Test 使用 TS3010a 和 v2 Prompt，API 计数从 29 增至 30，金标准召回 8/8。
- v2 结果经确定性证据修复后，结构和 evidence 校验问题为 0。
- v2 结果没有生成行动项或未决问题，符合该真实头脑风暴会议的保守金标准。
- 后续 Streamlit 和完整 QMSum 本地样例分析已切换为 v4 通用真实会议 Prompt，不再假设会议属于产品设计场景，并加强 owner 证据和 decision 边界。

## 未完成事实

- H4 人工验收尚未确认。
- 除 TS3010a 外，仓库内样例和完整数据集样例尚未制作人工金标准。
- v4 通用 Prompt 尚未执行新的金标准验收；TS3010a 的 8/8 gold 对照仍来自历史 v2 Smoke Test。
- 该附加实验不代表完整 QMSum benchmark 性能。
- 正式教材正文未编写。
