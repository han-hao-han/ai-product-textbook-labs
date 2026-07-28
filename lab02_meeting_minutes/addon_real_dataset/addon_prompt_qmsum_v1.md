# QMSum 附加实验 Prompt 草案

版本：`addon_prompt_qmsum_real_meeting_v1_draft`

## 附加约束

在主实验 Prompt 约束基础上，增加以下规则：

1. 输入来自 QMSum 的英文真实会议转写，输出可以使用英文。
2. 会议中可能存在 `{vocalsound}`、`{gap}`、`{disfmarker}` 等转写噪声，不要把噪声本身当作有效议题、决策或行动项。
3. brainstorming idea 不自动等于 decision。
4. 只有被主持人接受、复述、总结，或在多名参与者讨论后形成共同设计方向的内容，才可以写入 decisions。
5. 对 TS3010a，decisions 更接近“accepted product design requirements”，不是正式项目决议。
6. 没有明确负责人和截止日期时，不要生成 action_items。
7. 不要把 `Next instructions you'll get in your email` 扩展成具体行动项，因为原文没有说明具体交付物、负责人或截止日期。
8. 不要使用 QMSum 的 query answer 作为 evidence；evidence 必须来自 `Meeting Transcript`。
9. `Project Manager`、`Industrial Designer`、`Marketing`、`User Interface` 是角色型说话人，可作为 attendee name 输出。
10. 每条 evidence 仍必须是原文连续片段，不能拼接多轮发言。

## 预期抽取倾向

- action_items：保守，预计为空。
- decisions：抽取已被团队接受的遥控器设计要求。
- open_questions：保守，预计为空。
- topics：可包含绘图练习、遥控器使用经验、遥控器功能设计。

## v2 调整

版本：`addon_prompt_qmsum_real_meeting_v2_design_requirement_recall`

v2 基于第 1 次真实 Smoke Test 的漏召回问题补强：

1. 明确要求检查完整会议，不只抽取后段显性讨论。
2. 明确搜索早段产品目标：`original`、`trendy`、`user-friendly`。
3. 明确搜索预算约束：售价和制造预算。
4. 明确搜索低成本材料、兼容性、省电、按钮数量和按钮大小。
5. 明确 evidence 只能来自一个 transcript bullet line，不能跨说话人拼接。
6. 明确 `{vocalsound}`、`{gap}`、`{disfmarker}` 如果位于证据片段中，不得删除。

v2 真实 Smoke Test 结果：

- 结构校验：修复后通过。
- 金标准语义对照：8/8 召回。
- 行动项：保持为空。
- 未决问题：保持为空。

## v3 调整

版本：`addon_prompt_qmsum_real_meeting_v3_general_conservative`

v3 用于 Streamlit 和完整 QMSum 本地样例分析，不再假设输入是 Product 设计会议。

通用策略：

1. 不按 QMSum 的 Product/Academic/Committee 标签写死领域规则。
2. 自动从 transcript 判断会议意图；不确定时使用 conservative mode。
3. `decisions` 表示被会议确认、接受或作为后续依据的结论、选择、约束、实验设置、研究方向或规则，不再限定为产品设计要求。
4. `action_items` 表示明确后续工作、实验、分析、准备、实现、复核或协调；研究会议里的 “I will run...” 或 “I'm going to work on...” 可作为行动项。
5. `open_questions` 表示未解决问题、待验证假设、待复核取舍或明确留待之后确认的事项。
6. 普通建议、假设、`maybe`、`what if`、`I have an idea` 默认不是 decision，除非会议明确接受为后续依据。
7. 说话人标签可包含空格，例如 `Professor B`、`PhD D`、`Grad A`、`Project Manager`。

说明：

- v2 的 TS3010a 真实 Smoke Test 和 8/8 gold 对照结果保留为历史验收证据。
- v3 是后续探索完整 QMSum 样例的通用 Prompt；未重新声明 TS3010a gold 已由 v3 通过。

## v4 调整

版本：`addon_prompt_qmsum_real_meeting_v4_owner_decision_precision`

v4 基于 Bro021 v3 真实调用暴露的问题补强：

1. evidence 必须来自一个 transcript bullet line，禁止使用 `...` 省略号、摘要或多说话人拼接片段。
2. 每个 action_item 如果填写 owner，evidence 必须包含该 owner 的说话人标签，或同一行明确出现该 owner。
3. 其他人提出建议时，不能直接把建议对象推断成 owner；证据不足时 owner 设为 null 或不生成行动项。
4. 研究会议中的 `run experiments to see whether...` 默认是行动项或未决问题，不是 decision。
5. `what if`、`maybe`、`I have an idea` 仍默认不是 decision，除非后续被明确接受为计划。

说明：

- v4 是当前 Streamlit/QMSum 探索调用默认 Prompt。
- v4 尚未替代 TS3010a v2 gold 验收结论；若要宣称 v4 gold 通过，需要重新执行 TS3010a v4 真实调用和 gold 对照。
