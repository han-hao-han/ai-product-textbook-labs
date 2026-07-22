# 真实 API Smoke Test 记录

记录日期：2026-07-20

## 一、配置

- conda 环境：research_env
- Python：3.10.20
- Base URL：https://api.deepseek.com
- 模型 ID：deepseek-v4-flash
- Prompt 当前版本：prompt_v8_evidence_copy_guard_h3_draft
- Schema 当前版本：schema_v1_h3_draft
- 校验器当前版本：validator_v1_h3_draft

## 二、API 调用计数

当前预算文件记录：

```json
{
  "experiment": "1.5.2",
  "limit": 50,
  "used": 9,
  "remaining": 41,
  "warning_threshold": 40,
  "status": "active"
}
```

## 三、真实调用记录

### 第 1 次

- 输入：main/meeting_main_001.md
- 模式：single_pass
- 结果：真实 API 返回响应，但本地 `processing_metadata.usage` Schema 不支持嵌套 usage 对象，保存前失败。
- 是否计入预算：是

### 第 2 次

- 输入：main/meeting_main_001.md
- 模式：single_pass
- Prompt：prompt_v2_schema_contract_h3_draft
- 结果：真实 API 返回 JSON，但顶层结构不符合目标 Schema，出现 `agenda` 等错误字段。
- 是否计入预算：是

### 第 3 次

- 输入：main/meeting_main_001.md
- 模式：single_pass
- Prompt：prompt_v2_schema_contract_h3_draft
- 结果：保存结构化结果，validation_issues=8，主要为证据无法在原文中定位，并存在“先不做决策”被写入 decisions 的语义问题。
- 是否计入预算：是

### 第 4 次

- 输入：main/meeting_main_001.md
- 模式：single_pass
- Prompt：prompt_v3_evidence_decision_guard_h3_draft
- 结果：终端输出显示已保存结果，validation_issues=1。
- 是否计入预算：是

### 第 5 次

- 输入：main/meeting_main_001.md
- 模式：single_pass
- Prompt：prompt_v4_exact_evidence_guard_h3_draft
- 输出：lab02_meeting_minutes/outputs/real_main_smoke_v5.json
- 原始结构化响应：lab02_meeting_minutes/outputs/real_main_smoke_v5_raw.json
- 结果：真实 API 返回 JSON，结构校验、日期规范化、证据校验和负责人校验通过，validation_issues=0。
- 运行耗时：52.5383 秒。
- usage：prompt_tokens=1678，completion_tokens=7671，total_tokens=9349。
- 是否计入预算：是

## 四、当前可读取文件状态

第 4 次调用后，在后续文件系统清点时，真实结果文件不可见；当时可读取的结果目录只包含 Mock 结果文件：

- lab02_meeting_minutes/results/main_mock_result.json
- lab02_meeting_minutes/results/edge_003_mock_result.json

第 5 次调用已重新生成可读取的真实结果文件和 raw 文件，可作为 Smoke Test 过程证据。它仍不是最终验收证据，最终验收需等待固定回归、界面截图、事实包和 H4 人工验收。

## 五、结论

- 真实 API 可连通，模型能够返回 JSON。
- Prompt v4 已通过主案例真实 Smoke Test 的自动校验。
- 第 5 次调用后 API 预算为 used=5，remaining=45。
- H3 冻结前仍需确认语义金标准回归策略。

## 六、2026-07-20 Prompt 调整记录

第 4 次真实结果文件在当前工作区不可读取，因此无法确认剩余 1 个校验问题的具体字段。基于前 3 次和第 4 次记录中已知的主要问题类型，本轮只收紧 Prompt，不放宽校验器：

- Prompt 版本从 `prompt_v3_evidence_decision_guard_h3_draft` 升级为 `prompt_v4_exact_evidence_guard_h3_draft`。
- 增加 evidence 自检要求：每个 evidence 必须能作为原文连续子串直接搜索到。
- 增加决策/未决问题边界要求：只讨论、建议、考虑或等待结果的内容不得写入 decisions。
- 增加行动项 evidence 要求：证据必须覆盖任务和负责人；负责人由说话人身份表达时，可使用该说话人的完整原文句子。
- 校验策略保持严格，不把模糊匹配作为通过条件。

## 七、第 5 次真实结果与主金标准的非消耗对照

本对照只读取本地结果文件，不新增 API 调用。

| 项目 | 主金标准 | 第 5 次真实结果 |
|---|---:|---:|
| action_items | 8 | 7 |
| decisions | 2 | 2 |
| open_questions | 3 | 2 |
| validation_issues | 不适用 | 0 |

结论：

- 第 5 次真实调用通过了结构、日期、证据和负责人等自动校验。
- 第 5 次真实结果仍存在语义覆盖差异，例如少抽取 1 条行动项和 1 条未决问题。
- 因此，本次结论应表述为“真实 API Smoke Test 自动校验通过”，不能表述为“主案例语义金标准回归通过”。

补充：引入 `gold_compare_v1_h3_draft` 后，重新对比第 5 次真实结果，固定差异如下：

- 缺失 action_items：A008，准备客服培训说明。
- 缺失 decisions：D001，前端风险提示按二次确认方案实现。
- 多出 decisions：D002，确认退款接口异常码映射和联调验证由李明在下周三前完成。
- 缺失 open_questions：Q003，灰度上线前客服培训说明由谁负责。

基于上述差异，Prompt 升级为 `prompt_v5_gold_recall_guard_h3_draft`，新增规则：

- “按某方案实现”“只覆盖某范围”“不进入某范围”属于决策。
- 带负责人和截止日期的执行任务不得写入 decisions。
- 无负责人待办仍必须保留为 action_items，owner 为 null。
- “下次明确谁负责”类内容必须进入 open_questions。

## 八、第 6 次真实调用记录

- 输入：main/meeting_main_001.md
- 模式：single_pass
- Prompt：prompt_v5_gold_recall_guard_h3_draft
- 输出：lab02_meeting_minutes/outputs/real_main_smoke_v6.json
- 原始结构化响应：lab02_meeting_minutes/outputs/real_main_smoke_v6_raw.json
- 结果：真实 API 返回 JSON，结构校验、日期规范化、证据校验和负责人校验通过，validation_issues=0。
- API 预算：调用前 used=5，调用后 used=6，remaining=44。
- 语义对照：action_items 和 open_questions 已匹配主金标准；decisions 多抽 4 条项目管理安排。

第 6 次对照剩余问题：

- 多出 decisions：知识库标签本周必须收口。
- 多出 decisions：退款接口联调按计划推进。
- 多出 decisions：测试两步走：先完成三个场景回归，后补测退款场景。
- 多出 decisions：张琳在复核表里增加影响测试用例说明，赵强根据复核表更新测试用例。

基于上述差异，Prompt 升级为 `prompt_v6_decision_precision_guard_h3_draft`，新增规则：

- decisions 只记录产品范围、方案选择、验收结论或明确的业务规则变更。
- 项目管理安排、任务分配、联调计划、测试计划不写入 decisions。
- 同一事项如果已有负责人或截止日期，默认属于 action_items，不再重复写入 decisions。

## 九、第 7 次真实调用记录

- 输入：main/meeting_main_001.md
- 模式：single_pass
- Prompt：prompt_v6_decision_precision_guard_h3_draft
- 输出：lab02_meeting_minutes/outputs/real_main_smoke_v7.json
- 原始结构化响应：lab02_meeting_minutes/outputs/real_main_smoke_v7_raw.json
- API 预算：调用前 used=6，调用后 used=7，remaining=43。
- 自动校验：validation_issues=1。
- 自动校验问题：A006 的负责人赵强未出现在行动项证据中。
- 语义对照：ok=false。

第 7 次对照剩余问题：

- 多出 action_items：退款场景等接口联调完成后再补测。
- 多出 decisions：物流场景标签先保留现有标签。

基于上述差异，Prompt 升级为 `prompt_v7_split_and_suggestion_guard_h3_draft`，新增规则：

- “我建议……”“需要再看”“等数据回来再看”不是 decisions，除非主持人明确确认。
- 不把同一句话中分号后的条件性补测或后续补测拆成独立行动项。
- 行动项 evidence 必须能看到负责人姓名，或必须是负责人本人说出的完整原文句子。

## 十、第 8 次真实调用记录

- 输入：main/meeting_main_001.md
- 模式：single_pass
- Prompt：prompt_v7_split_and_suggestion_guard_h3_draft
- 输出：lab02_meeting_minutes/outputs/real_main_smoke_v8.json
- 原始结构化响应：lab02_meeting_minutes/outputs/real_main_smoke_v8_raw.json
- API 预算：调用前 used=7，调用后 used=8，remaining=42。
- 自动校验：validation_issues=5。
- 自动校验问题：A001、A002、A003、A008、Q002 的 evidence 无法在原文定位。
- 语义对照：ok=false，缺失 Q003。

第 8 次主要问题：

- 模型在人为截取的 evidence 前添加了“王芳：”前缀，导致 evidence 不是原文连续片段。
- 模型把原文中文引号改成单引号，导致 evidence 不是原文逐字片段。
- 客服培训说明已作为行动项抽出，但负责人待定未决问题漏抽。

基于上述差异，Prompt 升级为 `prompt_v8_evidence_copy_guard_h3_draft`，新增规则：

- evidence 不得人为添加说话人前缀。
- evidence 必须保留原文标点和引号。
- 同一段原文可同时支持无负责人行动项和负责人待定未决问题。
- 输出前必须把每个 evidence 当作搜索词在会议文本中搜索。

## 十一、第 9 次真实调用记录

- 输入：main/meeting_main_001.md
- 模式：single_pass
- Prompt：prompt_v8_evidence_copy_guard_h3_draft
- 输出：lab02_meeting_minutes/outputs/real_main_smoke_v9.json
- 原始结构化响应：lab02_meeting_minutes/outputs/real_main_smoke_v9_raw.json
- API 预算：调用前 used=8，调用后 used=9，remaining=41。
- 自动校验：validation_issues=0。
- 抽取数量：action_items=8，decisions=2，open_questions=3。
- 主金标准语义对照：ok=true，issues=[]。
- 结论：第 9 次真实主案例 Smoke Test 达到 H3 前主案例标准，可提交 H3 人工确认。
