# H3候选方案审阅

## 当前状态

```text
H0：已通过
H1：已通过
检查点1：已通过
H2：已通过
H3：比较规则v2已通过并实现；主样本最终参考结果已完成，H3已恢复冻结
```

本文件保留H3审阅证据。用户已于2026-07-23确认冻结该单一默认模型及其调用契约。

## 事实分级

| 内容 | 状态 | 依据 |
|---|---|---|
| 输出只含`fields + warnings` | 已从任务契约确认 | `docs/experiments/1.5.3_任务契约.md` |
| Qwen3.7 Plus支持图片输入 | 已从官方资料确认 | 阿里云百炼视觉理解文档 |
| Qwen3.7 Plus非思考模式支持结构化输出 | 已从官方资料确认 | 阿里云百炼视觉理解与结构化输出文档 |
| OpenAI-compatible接口支持本地图片Data URL | 已从官方资料确认 | 阿里云百炼OpenAI兼容接口文档 |
| 请求构造、解析、Schema和比较器 | 已通过Mock和单元测试确认 | 本实验自动测试 |
| 当前账号可调用固定模型 | 已通过真实运行确认 | `scripts/verify_h3_model.py`及本地运行记录 |
| 真实响应可解析并通过Schema v1 | 已通过真实运行确认 | 运行`20260722T172525_205760Z` |
| 主样本字段识别内容正确 | 已完成教学性人工裁决 | 检查点2真实结果、两层比较和用户原图裁决；不纳入正式验证 |

## 候选模型与调用方式

```text
provider = aliyun_model_studio
model = qwen3.7-plus-2026-05-26
base_url = https://dashscope.aliyuncs.com/compatible-mode/v1
api_style = openai_compatible_chat_completions
response_format = {"type": "json_object"}
enable_thinking = false
temperature = 0
timeout_seconds = 120
```

使用固定日期模型，而不是会滚动更新的别名。只设置一个候选，不开展多模型Benchmark。

官方资料：

- <https://help.aliyun.com/zh/model-studio/vision-model/>
- <https://help.aliyun.com/zh/model-studio/qwen-structured-output>
- <https://help.aliyun.com/zh/model-studio/qwen-api-via-openai-chat-completions>

## Prompt v1

文件：`prompts/form_extraction_v1.txt`

主要约束：

- 只提取明确识别且关系明确的键值对；
- 保留原始文字；
- 不根据常识补全；
- 标题和说明文字不默认作为字段；
- 不确定内容进入`warnings`；
- 只输出JSON，不输出分析或代码围栏；
- 不输出评分、置信度、比较状态和人工标注参考结果。

## Schema v1

文件：

- `schemas/form_extraction_v1.json`：读者可查看的JSON Schema；
- `src/schemas.py`：运行时Pydantic Schema。

模型输出严格限制为：

```json
{
  "fields": [{"key": "字段名", "value": "字段值"}],
  "warnings": []
}
```

顶层及字段项均禁止额外属性。程序生成的样本ID、模型、Prompt版本、Schema版本、运行时间和耗时不允许模型生成。

## 比较规则v2

文件：

- `src/dataset_annotation_comparator.py`：第一层数据集原始标注一致性；
- `src/reference_review.py`：人工复核状态校验和显式校正应用；
- `src/field_comparator.py`：只用于已确认或校正的最终参考结果。

第一层保留完全匹配和保守规范化匹配，其余统一表述为“值不一致”“配对不一致”“未在另一侧找到”。指标称为“数据集原始标注一致率”，不得解释为正确率。

程序另外提示包含关系、同值异键、复选符号差异、同键多行可能被模型合并、字段名或字段值高度相似。所有诊断提示均不自动判对。

只有人工结合原图把样本标记为`source_annotation_confirmed`或`human_corrected`后，程序才使用最终参考结果计算：

```text
参考字段识别正确率
```

`not_ready`和`rejected`状态不产生该指标，固定验证会在模型调用前停止。

## 已完成自动验证

已覆盖：

- 合法与非法Schema；
- 代码围栏、非JSON、空响应和Schema失败；
- 全角半角、空白、换行和key末尾冒号；
- 完全匹配、规范化匹配、错值、键值错配、遗漏和额外字段；
- 数据集原始标注一致率与两侧不一致状态；
- 包含关系、同值异键、复选符号、多行合并和高度相似诊断不自动判对；
- 未完成人工复核时不生成参考字段识别正确率；
- 主样本只有在人工复核状态可用时才生成参考字段识别正确率；
- 固定验证不检查最终参考结果状态，只验证调用和工程流程；
- 重复字段不合并；
- 人工复核必须填写原因；
- OpenAI-compatible图片请求构造；
- timeout失败记录脱敏；
- 失败不覆盖`current`；
- raw与parsed历史分开保存。

## 真实账号核验结果

```text
run_id = 20260722T172525_205760Z
sample_id = zh_train_103
model_requested = qwen3.7-plus-2026-05-26
model_returned = qwen3.7-plus-2026-05-26
finish_reason = stop
elapsed_seconds = 16.1181
usage = 已保存真实返回值
JSON解析 = 通过
Schema v1 = 通过
fields = 28
warnings = 0
current = 未更新
```

本地raw与parsed记录结构一致。检查未发现API Key、Authorization Header、Bearer、Cookie或完整请求头。

## H3冻结结果

用户已明确确认：

- `qwen3.7-plus-2026-05-26`为单一默认模型；
- 使用阿里云百炼OpenAI-compatible Chat Completions；
- 冻结Prompt v1；
- 冻结Schema v1；
- 冻结保守确定性比较规则。

该核验不替代新固定样本的读者体验，也不能证明字段内容正确。旧样本`zh_train_103`的运行记录只作为调用链历史证据保留。
