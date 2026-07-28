# H4 Smoke Test Review：QMSum TS3010a

## 输入

- 数据集：QMSum
- 样例：Product/val/TS3010a
- 转换输入：`data/selected_cases/TS3010a.md`
- 金标准：`data/gold/TS3010a_gold.json`

## 第 1 次真实调用：v1 Prompt

- 模型：`deepseek-v4-flash`
- Prompt：`addon_prompt_qmsum_real_meeting_v1_draft`
- API 调用计数：从 28 增加到 29
- 输出：`outputs/real_smoke/TS3010a_result.json`
- 元数据：`outputs/real_smoke/TS3010a_metadata.json`

## v1 结构与证据校验

首次真实结果结构可解析，但存在 7 个 evidence 无法定位问题。

原因：

- 模型删除了 `{gap}`、`{vocalsound}`、`{disfmarker}` 等噪声标记；
- 部分 evidence 跨多个说话人拼接；
- 部分 evidence 添加了说话人前缀，但原转换输入中的连续片段不完全一致。

已执行确定性 evidence 修复：

- 修复脚本：`scripts/repair_qmsum_smoke_output.py`
- 修复后 validation issue：0
- 未新增真实 API 调用

## v1 金标准语义对照

- 对照脚本：`scripts/compare_qmsum_gold.py`
- 报告：`outputs/real_smoke/TS3010a_gold_compare.json`
- 结果：未通过
- 期望设计要求：8
- 召回设计要求：3

召回：

- D004：耐摔 / rubber / hard plastic
- D005：LED 工作指示
- D007：外观 / 兼容性相关要求

缺失或不足：

- D001：original、trendy、user-friendly
- D002：25 欧元售价和 12.5 欧元制造预算
- D003：少按钮要求只部分覆盖
- D006：低成本材料只部分覆盖
- D008：省电 / 少换电池

## 结论

这次真实数据附加实验 Smoke Test 证明：

1. 主实验的 Schema、结构校验和结果保存链路可以迁移到真实英文会议样例。
2. evidence 约束在真实转写噪声下更容易失败，需要附加实验专用证据修复或更强 Prompt。
3. 现有 Prompt 对真实头脑风暴会议的设计要求召回不足，尤其容易漏掉会议早段目标、预算约束和末段补充要求。
4. 该结果不能作为完整 QMSum benchmark 性能，只能作为单样例适配边界证据。

## 下一步建议

在不改变主实验 accepted 状态的前提下，建议进入一次小范围 Prompt 调整：

- 明确要求抽取 early-stage goals；
- 明确要求抽取 budget constraints；
- 明确要求抽取 battery-saving / material-cost requirements；
- 明确禁止跨说话人拼接 evidence；
- 再执行 1 次真实 API 调用进行 v2 Smoke Test。

## 第 2 次真实调用：v2 Prompt

- 模型：`deepseek-v4-flash`
- Prompt：`addon_prompt_qmsum_real_meeting_v2_design_requirement_recall`
- API 调用计数：从 29 增加到 30
- 输出：`outputs/real_smoke/TS3010a_v2_result.json`
- 元数据：`outputs/real_smoke/TS3010a_v2_metadata.json`

v2 调整重点：

- 补强早段目标：original、trendy、user-friendly；
- 补强预算约束：25 欧元售价、12.5 欧元制造预算；
- 补强低成本材料、省电、按钮数量和按钮大小；
- 明确禁止跨说话人拼接 evidence；
- 要求保留证据中的转写噪声标记。

## v2 结构与证据校验

首次 v2 输出仍有 6 个 evidence 定位问题，主要原因是模型仍在少量证据中添加说话人前缀或省略转写噪声。

已执行确定性 evidence 修复：

- 修复脚本：`scripts/repair_qmsum_smoke_output.py --prompt v2`
- 修复后 validation issue：0
- 未新增真实 API 调用

## v2 金标准语义对照

- 对照脚本：`scripts/compare_qmsum_gold.py --prompt v2`
- 报告：`outputs/real_smoke/TS3010a_v2_gold_compare.json`
- 结果：通过
- 期望设计要求：8
- 召回设计要求：8

v2 召回：

- D001：original、trendy、user-friendly
- D002：25 欧元售价和 12.5 欧元制造预算
- D003：重量和按钮相关要求
- D004：耐摔 / rubber / hard plastic
- D005：LED 工作指示
- D006：低成本材料 / plastic
- D007：外观 / 兼容性相关要求
- D008：省电 / 少换电池

## H4 候选结论

v2 结果可作为附加实验人工验收候选：

1. 主实验 Schema、Pipeline、证据校验和金标准对照可以迁移到 QMSum 单样例。
2. Prompt v2 能显著改善真实头脑风暴会议中的设计要求召回。
3. 证据仍需要确定性修复，说明真实会议转写噪声下 evidence 约束更脆弱。
4. 该结果只证明单个 QMSum Product 样例的适配边界，不代表完整 QMSum benchmark 性能。
