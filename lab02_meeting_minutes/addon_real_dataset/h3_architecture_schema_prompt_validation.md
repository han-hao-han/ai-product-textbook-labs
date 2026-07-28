# H3 设计：真实 QMSum 样例的架构、Schema、Prompt、校验和回归方案

## 当前结论

附加实验优先复用 1.5.2 主实验链路，不改变主实验 `accepted` 状态。

```text
QMSum 主样例或本地完整数据集转换输入
→ 复用 CLI / Pipeline
→ 复用 deepseek-v4-flash 默认模型
→ 使用真实会议 Prompt 附加约束
→ 复用 MeetingExtractionResult Schema
→ 复用证据校验、日期规范化和金标准语义对照
→ 单独保存附加实验输出与事实记录
```

## 架构边界

| 模块 | H3 方案 |
|---|---|
| 输入 | `addon_real_dataset/data/selected_cases/TS3010a.md`；Streamlit 可选择仓库内三样例或本地完整缓存样例 |
| 数据来源 | QMSum 官方仓库审计样例；完整数据集由用户本地下载 |
| 原始数据 | 不提交完整 QMSum 数据集，完整缓存写入 `data/downloads/qmsum_full/` |
| 输出目录 | `addon_real_dataset/outputs/` |
| 金标准 | `addon_real_dataset/data/gold/TS3010a_gold.json` |
| 主实验锁 | 不修改主实验 `accepted` 结论 |
| 真实 API | H3 不调用；H3 确认后再做 1 次 Smoke Test |

## Schema 方案

复用主实验 `MeetingExtractionResult`：

- `topics`
- `decisions`
- `action_items`
- `open_questions`
- `meeting_summary`
- `processing_metadata`
- `validation_issues`

原因：

- 附加实验目标是测试现有链路边界，而不是新建独立抽取任务。
- TS3010a 仍可表达为会议输入、议题、设计要求、行动项和未决问题。
- 金标准草案采用低密度抽取，避免要求真实会议具备虚构样例的强结构。

## Prompt 适配原则

主实验 Prompt 可以复用，但附加实验需要增加以下真实会议约束：

1. 输入是英文真实会议转写，输出可以使用英文。
2. 真实会议中的 brainstorming idea 不自动等于 decision。
3. 只有被主持人接受、复述、总结或 QMSum 主题答案支持的设计要求，才进入 decisions。
4. 没有明确负责人和截止日期时，不要生成 action_items。
5. `Project Manager`、`Industrial Designer`、`Marketing`、`User Interface` 是角色型说话人，不是需要脱敏的真实姓名。
6. `{vocalsound}`、`{gap}`、`{disfmarker}` 是转写噪声，不应单独作为 evidence。
7. evidence 仍必须可定位到原文；校验时允许忽略 `{vocalsound}`、`{gap}`、`{disfmarker}` 等真实转写噪声标记。

建议版本名：

```text
addon_prompt_qmsum_real_meeting_v1_draft
```

## 校验器方案

优先复用主实验校验器：

- 结构校验；
- evidence 是否可在原文定位，且定位时容忍真实转写噪声标记；
- 日期规范化；
- 决策/未决问题冲突检查；
- 金标准语义对照。

需要注意的真实数据差异：

- QMSum 说话人可能包含空格，例如 `Project Manager`。
- 当前主实验 owner 校验主要面向中文姓名和无空格英文 token。
- TS3010a 金标准不包含行动项，因此短期不触发 owner 校验风险。
- 若后续真实样例包含行动项，需要新增附加实验专用 speaker regex 或扩展主校验器；扩展前必须评估对主实验的影响。

## 回归方案

H3 确认后建议执行：

1. 转换脚本回归：重新读取官方审计样例并生成 `TS3010a.md`、`IS1003a.md`、`ES2011a.md`。
2. JSON 格式检查：`addon_lock.json`、`external_manifest.json`、`TS3010a_gold.json`。
3. Mock/结构链路检查：使用固定 mock 或最小构造结果验证 Schema 和证据校验。
4. 真实 API Smoke Test：只对 `TS3010a.md` 调用 1 次 `deepseek-v4-flash`。
5. 金标准语义对照：重点检查 8 条设计要求召回情况，且不应生成虚构负责人/日期行动项。

## 验收标准

### A 级

- 输出 JSON 通过 Schema。
- 所有 evidence 可在 `TS3010a.md` 中定位；允许忽略 `{vocalsound}`、`{gap}`、`{disfmarker}` 等转写噪声标记。
- 不生成带虚构负责人或截止日期的行动项。
- 至少召回主要设计要求：易用、预算、重量/按钮、耐摔、LED、材料/成本、兼容性、电池。

### B 级

- 允许模型把“设计要求”表述为 decisions 或 topics，但必须有证据。
- 允许遗漏少数细粒度设计点，但必须保留整体产品方向。

### C 级

- 不得输出与原文无关的产品背景。
- 不得把 QMSum 原始 query answer 当作会议原文 evidence。
- 不得声称附加实验代表完整 QMSum benchmark 性能。
- 对没有人工金标准的 QMSum 样例，不得声称 gold 验收通过。

## H3 待确认

请确认是否同意：

- 复用主实验 Schema、Pipeline、证据校验和日期规范化；
- 为 QMSum 附加实验增加 Prompt 附加约束；
- H3 确认后只做 1 次真实 API Smoke Test；
- 结果单独保存到 `addon_real_dataset/outputs/`，不改变主实验 `accepted` 状态。
