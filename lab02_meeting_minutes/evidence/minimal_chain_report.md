# 最小可运行链路报告

生成日期：2026-07-20

## 一、运行环境

- conda 环境：research_env
- Python：3.10.20
- pytest：9.1.1
- pydantic：2.13.4

## 二、Mock 链路

当前 Mock 链路已实现：

- 内部 CLI；
- 主案例读取；
- Mock LLM 客户端；
- 结构校验；
- 日期规范化；
- 证据校验；
- 负责人校验；
- 结果保存。

## 三、测试结果

命令：

```powershell
conda run -n research_env python -m pytest lab02_meeting_minutes/tests
```

结果：

```text
15 passed, 1 warning
```

warning 来自 pytest 无法写入 `.pytest_cache`，不影响测试结果。

## 四、Mock CLI 结果

### 主案例

```text
saved: lab02_meeting_minutes\results\main_mock_result.json
mode: single_pass
validation_issues: 0
```

### 无会议日期相对日期边界

```text
saved: lab02_meeting_minutes\results\edge_003_mock_result.json
mode: single_pass
validation_issues: 0
```

### H2 全量样例

```text
checked=15 failures=0
```

覆盖范围：

- main：1 个样例；
- demo：3 个样例；
- regression：5 个样例；
- edge：6 个样例。

## 五、Prompt 调整

- 当前 Prompt 版本：`prompt_v8_evidence_copy_guard_h3_draft`。
- 调整原因：第 4 次真实调用记录显示仍有 1 个校验问题，但真实结果文件在当前工作区不可读取，无法确认具体字段。
- 调整策略：收紧 evidence 逐字连续子串要求、决策/未决问题边界、行动项证据覆盖范围；校验器保持严格。

## 六、主金标准语义对照

当前已实现 `gold_compare_v1_h3_draft`，用于固定检查主金标准中 action_items、decisions、open_questions 的召回情况。

第 5 次真实结果对照结果：

```text
ok=false
missing action_items: A008
missing decisions: D001
unexpected decisions: D002
missing open_questions: Q003
```

第 6 次真实结果对照结果：

```text
ok=false
unexpected decisions: D001, D002, D004, D006
```

第 6 次结果已匹配 action_items 和 open_questions 的主金标准召回，剩余问题是 decisions 多抽。Prompt 已升级到 v6，用于下一次真实调用验证。

第 7 次真实结果对照结果：

```text
validation_issues=1
unexpected action_items: A006
unexpected decisions: D001
```

第 7 次结果没有达标。Prompt 已升级到 v7，用于约束建议类内容不进 decisions，并避免把条件性补测拆成独立行动项。

第 8 次真实结果对照结果：

```text
validation_issues=5
missing open_questions: Q003
```

第 8 次结果没有达标。Prompt 已升级到 v8，用于修复 evidence 人为添加说话人前缀、引号改写，以及客服培训负责人待定问题漏抽。

第 9 次真实结果对照结果：

```text
validation_issues=0
gold_compare ok=true
issues=[]
```

第 9 次结果达到主案例 H3 前标准：真实 API 可连通、结果可保存、自动校验通过、主金标准语义对照通过。

## 七、限制

- 当前 Mock 结果不是真实模型输出。
- 第 5 次真实调用已重新保存可追溯真实结果，自动校验通过；但它与主金标准仍有语义覆盖差异，不能作为语义回归通过结论。
