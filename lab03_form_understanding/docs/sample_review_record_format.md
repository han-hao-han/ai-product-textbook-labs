# XFUND教学样本人工复核记录格式

## 目的

每张最终教学样本必须同时保存：

1. 原图隐私复核；
2. XFUND原始显式关系的标注复核；
3. 所有人工校正；
4. 最终人工标注参考结果的形成状态。

机器可校验格式位于：

```text
schemas/sample_review_record_v1.json
```

## 隐私复核

`national_id`是硬性判断：

| 值 | 含义 |
|---|---|
| `not_reviewed` | 尚未人工查看原图 |
| `not_present` | 已查看，未发现完整、局部或遮挡的身份证号码 |
| `present` | 发现身份证号码，样本必须淘汰 |
| `uncertain` | 无法确认，样本不得进入正式集合 |

姓名允许出现。电话、地址、账号、签名等写入`other_signal_categories`和`notes`，但不自动淘汰。

复核记录不得抄录身份证号码，也不得在备注中保存其局部数字。

## 标注复核

`annotation_review.status`含义：

| 值 | 含义 |
|---|---|
| `pending` | 尚未复核 |
| `confirmed` | 原始显式question-answer关系可直接作为参考 |
| `corrected` | 已保存一项或多项人工校正 |
| `rejected` | 错误过多或无法可靠校正，不适合作为教学样本 |

每项`corrections`必须记录：

- 操作类型；
- 可追踪的原始实体ID；
- 原字段；
- 校正后字段；
- 校正原因；
- 证据来自原图、原始标注或两者。

不得静默覆盖XFUND原始标注。程序后续应读取：

```text
XFUND原始显式关系
＋人工校正记录
→ 最终人工标注参考结果
```

## 同名多行与合并

同一字段名在XFUND中可能链接到多个分行值，而视觉模型可能把版面上的多行内容合并为一个值。程序只给出：

```text
same_key_multiple_dataset_values_combined
```

作为复核提示，不自动判断哪种表示更正确。

人工若确认原图应保留多个独立字段，可以确认原标注；若确认教学参考应合并为一个字段，应使用：

```text
replace_value（把保留字段改为合并值）
＋
remove_field（删除其余重复关系）
```

每一步均需引用原始question/answer实体ID并填写原因。不得只为了提高模型结果而合并。

字段名或字段值“大部分相同”同样只产生带分数的诊断提示。当前字符相似度阈值为`0.75`，不参与自动判对。

## 表格行列结构

XFUND显式关系可能按字段名分组，无法直接表达“多行多列”中每个值属于哪一行。人工确认这类结构后，使用`annotation_review.structure_reviews`记录：

- 原始复核页字段序号；
- 行数、列数和列名；
- 每个单元格对应的question/answer实体ID；
- 稳定的`row_id`与`column_index`；
- 原图裁决原因。

结构记录不会改变模型Schema v1，也不会把一行自动拼成一个字段。最终参考字段仍保持可比较的键值对，同时附带`structure_group_id`、`structure_row_id`和`structure_column_index`供审计。当前字段正确率仍是扁平键值指标，不能单独衡量整行关联是否正确，这一点必须作为实验限制说明。

## 评价形成时点

`evaluation_context`用于防止把模型运行后形成的参考结果伪装成模型运行前冻结的正式答案。

主样本或观察样本可以用于教学性人工裁决：

```text
reference_frozen_before_model_run = false
usage = teaching_post_run_adjudication_only
included_in_formal_validation = false
```

这类结果可以展示模型与原始标注的差异，以及人工为什么支持某种语义表达，但不得进入正式验证统计。

若未来另行开展基于人工冻结参考结果的正式内容正确率评测，固定验证样本才必须在任何模型调用前完成：

```text
reference_frozen_before_model_run = true
usage = pre_model_frozen_reference
included_in_formal_validation = true
```

当前1.5.3的6张固定样本只用于视觉模型调用和工程流程验证，不启用上述内容正确率门禁。已有记录可作为可选诊断笔记保留；不得据此声称已形成正式内容正确率评测。

## 特殊符号

`☑`、`□`、`☒`、`✓`、`✔`、`√`和`■`可能表达复选框状态，不是可以默认删除的噪声。

统一规则：

```text
保留原始符号
不自动把☑等价为“是”“选中”或“符合”
不自动把□等价为“否”“未选中”或“不符合”
不把不同复选符号自动互换
由人工结合原图逐字段确认语义和键值关系
```

若人工决定改写为语义值，必须在`corrections`中记录原字段、校正字段、原因和证据，不能修改XFUND原文件。

## 最终状态

只有以下两种状态可进入正式比较：

```text
source_annotation_confirmed
human_corrected
```

`not_ready`和`rejected`仍可用于第一层“数据集原始标注一致性”观察，但不得计算最终参考字段正确率。它们可以进入当前1.5.3的固定工程验证，因为该验证不评价内容正确率。

单张比较流水线会生成“数据集原始标注一致率”；但在上述两种可用状态形成前，`final_reference_comparison`为`null`，不生成“参考字段识别正确率”。固定工程验证不读取最终参考结果门禁，原始标注一致率仅作为可选诊断。
