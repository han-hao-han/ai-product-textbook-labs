# 基于视觉大模型的中文表单结构化识别助手

当前状态：H0至H4均已通过。教材主样本`zh_train_136`保留完整两层比较与教学性人工裁决；6张固定样本已在Streamlit中按冻结顺序完成真实串行调用，结果为6张成功、0张失败。固定验证只用于视觉模型调用和工程流程验证，不要求逐字段修复XFUND原始标注，也不计算参考字段识别正确率。实验工程与读者体验流程完成，正式教材正文待人工编写。

本实验使用XFUND v1.0中文表单，帮助读者理解：

```text
真实中文表单图片
→ 视觉模型提取fields + warnings
→ 程序进行Schema校验
→ 主样本与XFUND原始标注进行严格一致性比较
→ 主样本由人工结合原图确认或校正最终参考结果
→ 仅对主样本的最终参考结果计算教学性参考字段识别正确率
→ 6张固定样本验证串行调用、失败记录和工程流程
→ Streamlit产品体验
```

数据与样本已冻结。阶段3先完成Mock、Schema和确定性比较测试，再由用户显式触发一次候选模型核验。

## 数据许可

XFUND官方仓库：<https://github.com/doc-analysis/XFUND>

数据按`CC BY-NC-SA 4.0`用于本项目的非商业教学实验：

- 保留来源与许可署名；
- 标明本项目进行了筛选和结构转换；
- 派生数据遵循相同许可；
- 不在仓库中重新分发原始图片或完整标注。

许可文本：<https://creativecommons.org/licenses/by-nc-sa/4.0/>

## 阶段2数据流

```text
GitHub官方Release
→ data/raw/xfund_v1.0/
→ JSON与图片一致性检查
→ 显式question-answer关系转换
→ data/local/candidate_manifest.json
→ data/local/candidate_gallery.html
→ 用户人工选择主样本和观察样本
```

`data/raw/`和`data/local/`只保存在本地，已由本实验目录的`.gitignore`排除。

## 检查点1命令

在本目录中运行：

```powershell
& "D:\DevelopTool\Anaconda\shell\condabin\conda-hook.ps1"
conda activate research_env
python --version
python scripts/download_xfund.py --split train
python scripts/inspect_candidates.py
```

第一行只为当前PowerShell窗口加载Conda钩子，不修改PowerShell配置文件。当前已验证`research_env`使用Python 3.10.20。

如果不需要显示激活环境，也可以使用等效的无激活方式：

```powershell
conda run -n research_env python --version
conda run -n research_env python scripts/download_xfund.py --split train
conda run -n research_env python scripts/inspect_candidates.py
```

然后在浏览器中打开程序输出的：

```text
data/local/candidate_gallery.html
```

请逐张观察：

- 真实表单图片；
- 实体标签数量；
- 显式键值关系数量；
- 转换后的人工标注参考字段；
- 字段长度和键值空间距离；
- 转换警告。

候选页只帮助查看，不会自动选定教材主样本或观察样本。

## H2重新确认的主样本和观察样本

按“身份证号码硬排除、其他隐私信号只记录”的规则重新查看后，用户已确认：

```text
教材主样本：zh_train_136
观察样本1（字段较多）：zh_train_115
观察样本2（键值距离较远）：zh_train_16
观察样本3（布局较复杂）：zh_train_29
```

固定配置保存在：

```text
configs/teaching_subset.json
```

4张样本的原图均经用户确认未发现身份证号码。主样本已完成逐字段复核和校正；观察样本可按需查看原始标注诊断，但不要求逐字段修复。XFUND原始标注不能写成100%正确。

## 固定验证候选

验证候选必须在模型运行前产生，并排除上述4张样本。生成命令：

```powershell
& "D:\DevelopTool\Anaconda\shell\condabin\conda-hook.ps1"
conda activate research_env
python scripts/build_teaching_subset.py
Start-Process .\data\local\validation_candidate_gallery.html
```

难度分数使用以下标注和布局特征：

| 特征 | 权重 |
|---|---:|
| 人工标注参考字段数 | 30% |
| 实体数 | 20% |
| 最长字段值字符数 | 15% |
| 多行实体数 | 15% |
| 键值平均空间距离 | 15% |
| 重复键名数 | 5% |

程序按分数排序后分成简单、中等、较复杂三个候选池，并从每个候选池均匀抽取4张。该分数不使用模型正确率或模型错误数量；用户仍需每类人工选择2张。

H2已重新确认以下固定验证顺序：

```text
简单1：zh_train_30
简单2：zh_train_85
中等1：zh_train_58
中等2：zh_train_65
较复杂1：zh_train_132
较复杂2：zh_train_141
```

组内顺序采用用户明确给出的顺序。固定验证集不得根据后续模型表现调整。

## 阶段3：H3候选契约

### 候选视觉模型

当前候选为：

```text
模型：qwen3.7-plus-2026-05-26
服务：阿里云百炼
接口：OpenAI-compatible Chat Completions
模式：非思考模式 + response_format=json_object
状态：模型和调用方式已核验；H3比较规则v2已通过并实现；固定验证工程流程已实现
```

选择固定日期版本是为了避免模型别名升级后教材结果静默变化。官方视觉理解文档将Qwen3.7 Plus作为视觉任务的推荐起点，并说明它支持图片输入和结构化输出：

- <https://help.aliyun.com/zh/model-studio/vision-model/>
- <https://help.aliyun.com/zh/model-studio/qwen-structured-output>
- <https://help.aliyun.com/zh/model-studio/qwen-api-via-openai-chat-completions>

配置保存在`configs/model_candidate.json`。固定模型仍为单一候选，不开展多模型横向比较。比较规则v2、主样本人工参考复核流程和读者入口均已验证，H3已恢复为`h3_frozen_user_confirmed`。固定验证不以逐样本参考结果复核为门禁。

### Prompt与Schema

```text
Prompt：prompts/form_extraction_v1.txt
Prompt版本：v1
JSON Schema：schemas/form_extraction_v1.json
Pydantic实现：src/schemas.py
Schema版本：v1
```

模型只能返回：

```json
{
  "fields": [
    {"key": "字段名", "value": "字段值"}
  ],
  "warnings": []
}
```

模型不得返回置信度、比较状态、样本ID或人工标注参考结果。代码围栏、非JSON、额外字段和错误类型都会被程序拒绝。

### 程序比较规则v2

第一层由`src/dataset_annotation_comparator.py`执行：

```text
完全匹配
→ 保守规范化后匹配
→ 值不一致或配对不一致
→ 模型输出中未找到或数据集原始标注中未找到
→ 数据集原始标注一致率
```

包含关系、同值异键、复选符号差异、同键多行可能合并以及字符高度相似只作为诊断提示，不自动判对。第一层指标不代表模型正确率。

第二层由`src/reference_review.py`读取人工复核和显式校正。只有最终状态为`source_annotation_confirmed`或`human_corrected`时，`src/field_comparator.py`才计算“参考字段识别正确率”。原始XFUND标注不会被覆盖。

## H3真实账号核验

本实验使用目录内独立`.env`，不读取或修改旧实验配置。不要把API Key粘贴到聊天、README或终端输出中。

本项目已于2026-07-23（北京时间）完成一次核验，无需无意义重复调用：

```text
样本：zh_train_103
请求模型：qwen3.7-plus-2026-05-26
返回模型：qwen3.7-plus-2026-05-26
finish_reason：stop
耗时：16.1181秒
JSON解析：通过
Schema v1：通过
fields：28
warnings：0
current：未更新
敏感元数据检查：通过
```

该结果只证明调用链和输出结构可用，不证明28个字段内容正确。

在本目录运行：

```powershell
& "D:\DevelopTool\Anaconda\shell\condabin\conda-hook.ps1"
conda activate research_env
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
notepad .env
python scripts/verify_h3_model.py
```

请在记事本中填写自己的`LLM_API_KEY`后保存。命令会把已通过隐私检查的教材主样本图片发送给阿里云百炼，产生一次真实模型调用；不会比较正确率，也不会更新`results/current/`。

正常结果应同时显示：

- 真实调用成功；
- JSON解析成功；
- Schema v1校验成功；
- `fields`和`warnings`数量；
- 本地raw和parsed文件路径。

失败会明确区分模型调用、空响应、JSON解析和Schema校验阶段。历史raw、parsed和failed记录只保存在本地，不提交仓库。

## 当前未完成

- 正式教材正文仍待人工编写；
- 经脱敏、适合提交仓库的正式示例结果暂不提交；
- 观察样本和固定样本的逐字段复核仅为可选诊断，不是完成门禁。

## 检查点2：第一次视觉结构化识别

H3核验历史不得替代本次读者体验。用户需要主动运行：

```powershell
& "D:\DevelopTool\Anaconda\shell\condabin\conda-hook.ps1"
conda activate research_env
python scripts/step02_extract_form.py
```

默认输入读取当前H2配置，因此现在是教材主样本`zh_train_136`。主样本人工参考复核已完成，H3调用门禁已重新冻结；用户明确触发后，本命令会产生一次真实模型调用，并依次展示：

- 图片来源和固定模型；
- 模型原始响应；
- JSON解析状态；
- Schema v1校验状态；
- `fields`和`warnings`；
- raw、parsed和current保存位置。

只有调用、解析和Schema全部成功后才会更新`results/current/zh_train_136.json`。失败记录进入`results/failed/`，既有current不会被覆盖。

运行后必须暂停并确认检查点2。此时不要直接开始结果比较，因为结构合法仍不代表字段正确。

### 历史运行（旧主样本，仅保留为链路证据）

用户已于2026-07-23（北京时间）主动完成检查点2正式运行：

```text
run_id：20260722T173933_965242Z
样本：zh_train_103
模型：qwen3.7-plus-2026-05-26
Prompt：v1
Schema：v1
finish_reason：stop
耗时：17.01秒
fields：28
warnings：0
raw、parsed、current：内容一致
失败记录：0
敏感元数据检查：通过
```

该记录发生在重新选样和比较规则修订前，只证明当时的正式识别链路成功，不能代表当前主样本或比较规则v2的结果。

## 检查点3：两层比较

本步骤不调用模型，默认读取当前主样本的：

```text
results/current/zh_train_136.json
```

用户运行：

```powershell
python scripts/step03_compare_result.py
```

如需比较某次历史parsed结果，可显式指定：

```powershell
python scripts/step03_compare_result.py --sample-id zh_train_136 --result-file <历史parsed文件>
```

第一层将模型字段与XFUND显式question-answer关系逐一比较，展示：

- 完全一致和规范化后一致；
- 值不一致和配对不一致；
- 两侧独有字段；
- 包含、同值异键、复选符号、多行合并和高度相似诊断；
- 数据集原始标注一致率。

第二层读取`data/local/sample_reviews/<sample_id>.json`。只有人工确认或校正后的最终参考结果可用时，才展示“参考字段识别正确率”；否则明确显示暂不计算。

比较结果保存到`results/comparisons/`。程序不会调用模型、修改模型输出、覆盖XFUND原始标注或把诊断提示自动判为正确。

### 当前主样本检查点3结果

用户已于2026-07-23完成两层比较和最终人工裁决：

```text
模型run_id：20260723T082446_019382Z
最终比较run_id：20260723T091432_796099Z
XFUND原始标注字段数：26
数据集原始标注一致率：30.77%
最终语义参考字段数：19
教学性参考字段识别正确率：100.00%
评价范围：模型运行后的教学性人工裁决
正式验证统计：不纳入
```

人工裁决包括：复选组仅保留选中业务值；两组表格使用带行号字段保存对象关联；删除被XFUND重复关联的说明文字字段。

### 历史检查点3（旧规则与旧主样本）

用户已运行检查点3，比较来源为检查点2的同一次正式模型结果：

```text
模型run_id：20260722T173933_965242Z
比较run_id：20260722T175508_526301Z
人工标注参考字段数：29
完全匹配：20
规范化后匹配：0
值错误：4
键值错配：0
遗漏：5
额外字段：4
人工复核：0
参考字段识别正确率：68.97%
```

该`68.97%`来自旧规则直接把XFUND原始标注当作参考答案的历史比较。发现原始标注质量问题后，该结果不再称为当前有效的“参考字段识别正确率”，也不得用于说明当前固定主样本或模型通用表现。

## 逐字段人工复核

主样本逐字段复核已完成；如需复查或查看校正记录，可重新生成本地复核页：

```powershell
conda activate research_env
python scripts/inspect_reference_review.py
```

输出：

```text
data/local/reference_review_zh_train_136.html
```

`zh_train_30`和`zh_train_85`已有的局部复核记录作为本地诊断笔记保留，不要求继续扩展到全部固定样本，也不参与固定验证工程指标。

页面并排展示原图、原始字段、question/answer实体ID、已记录校正、两行三列结构、同名多行提示和复选符号提示。最终复核记录保存在`data/local/sample_reviews/zh_train_136.json`；原始标注保持不变。

主样本的最终参考结果是在检查点2模型运行后由用户结合原图裁决形成：

- 复选组只保留人工确认的选中业务值；
- 两行三列表格使用带行号的语义字段保存对象关联；
- `evaluation_context.usage = teaching_post_run_adjudication_only`；
- 不纳入6张正式固定验证统计。

只有未来另行开展正式内容正确率评测时，验证样本才需要在模型运行前形成并冻结参考结果，记录为`pre_model_frozen_reference`。当前6张固定样本只验证调用和工程流程，不读取该门禁。

## 分步骤入口

```text
scripts/step01_inspect_data.py      查看真实图片、标注摘要和人工标注参考结果
scripts/step02_extract_form.py      调用固定视觉模型并保存raw、parsed和current
scripts/step03_compare_result.py    确定性比较，不调用模型
scripts/step04_run_validation.py    串行运行6张固定验证样本
scripts/inspect_reference_review.py 生成逐字段人工复核页，不调用模型
```

观察样本可以用`--sample-id`逐张运行step01至step03，但不得生成3张观察样本综合指标，也不得并入正式验证。

`step04_run_validation.py`是固定验证的命令行入口。检查点4要求在Streamlit中点击“运行固定验证”，因此两种入口不应无意义连续重复运行。

## Streamlit检查点4

状态：已于2026-07-23由用户现场完成并确认H4通过。

启动命令：

```powershell
& "D:\DevelopTool\Anaconda\shell\condabin\conda-hook.ps1"
conda activate research_env
streamlit run app.py
```

应用包含两个标签页：

```text
单张表单识别
验证结果
```

### 单张表单识别

内置：

- 教材主样本；
- 观察样本1：`zh_train_115`；
- 观察样本2：`zh_train_16`；
- 观察样本3：`zh_train_29`；
- 上传自定义图片。

检查点4建议选择任意一张观察样本，勾选一次调用确认后点击“运行单张识别”。这可以完成“至少1张观察样本真实运行”的验收要求。

自定义图片限制为JPEG、PNG或WebP，最大10MB。文件使用程序生成的安全名称保存到被忽略的`data/local/uploads/`。自定义输入没有人工标注参考结果，界面只检查结构，不能自动判断内容是否正确。

### 验证结果

H2已确认以下固定验证顺序。程序按该顺序串行调用，不根据模型表现调整样本或顺序：

```text
zh_train_30
zh_train_85
zh_train_58
zh_train_65
zh_train_132
zh_train_141
```

单张失败会记录原因并继续，最终明确标记验证是否完整。验证输出保存到`results/validations/`，并展示逐样本的成功或失败、识别字段数、warnings数、耗时，以及难度分组和总体工程汇总。

固定验证不要求6张样本具有已完成的最终参考结果，不计算“参考字段识别正确率”。XFUND原始标注一致性仍可生成，但只作为可选诊断，不代表模型内容正确率。

本次现场结果为6张成功、0张失败、共148个fields、3条warnings；总模型调用耗时94.9504秒。单张页面中语义相同但字段命名形式不同的内容可能被严格比较标记为“遗漏/额外字段”，该状态只表示字段键未严格对应，不代表模型内容错误。

页面重新渲染、切换标签页、展开原始响应、查看比较和下载JSON不会调用模型。重新运行必须再次点击按钮并确认。

适合截图的区域是：单张页的图片与比较汇总，以及验证页的逐样本状态、难度汇总和完整性。截图前应隐藏本地路径、自定义敏感内容和不必要的字段值；Codex不生成或选择截图。
