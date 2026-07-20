# ASAP 数据集使用与许可说明

## 1. 数据集信息

* 数据集名称：ASAP
* 完整名称：A Chinese Review Dataset Towards Aspect Category Sentiment Analysis and Rating Prediction
* 发布组织：Meituan-Dianping
* 官方仓库：https://github.com/Meituan-Dianping/asap
* 固定数据版本：`975122a60065240124df62cb4d5dbfd19ed9ef2c`
* 对应论文：Bu et al., “ASAP: A Chinese Review Dataset Towards Aspect Category Sentiment Analysis and Rating Prediction,” NAACL 2021
* 论文页面：https://aclanthology.org/2021.naacl-main.167/
* 原始许可证：Apache License 2.0

## 2. 本项目的数据使用方式

本项目不重新分发完整 ASAP 数据集。

完整原始文件仅由使用者通过项目提供的下载脚本，从 ASAP 官方 GitHub 仓库获取，并保存在：

`lab01_feedback_analysis/data/raw/`

该目录已加入 `.gitignore`，不会提交到项目 Git 仓库。

本项目仅分发以下教学固定子集：

* `feedback_main_1.csv`
* `feedback_demo_5.csv`
* `feedback_regression_20.csv`
* `feedback_extension_100.csv`

这些子集由 ASAP 原始数据确定性筛选得到，用于大模型用户反馈分析实验、课堂演示和人工回归验证。

## 3. 修改说明

与官方原始文件相比，本项目对固定子集进行了以下处理：

1. 将 `id` 映射为 `review_id`；
2. 将 `review` 映射为 `review_text`；
3. 将 `star` 映射为 `source_star`；
4. 将官方 18 个细粒度评价标签确定性合并为五个粗粒度参考维度：

   * `location`
   * `service`
   * `price`
   * `environment`
   * `food`
5. 增加数据来源划分和子集用途字段；
6. 按固定记录 ID、固定筛选规则和固定哈希排序生成教学子集；
7. 对教材演示集进行了人工隐私和展示适宜性检查。

五个粗粒度情感字段来自 ASAP 原始人工标签的确定性映射，仅作为实验验证参考，不是大语言模型生成结果。

## 4. 可复现性

数据来源、原始文件 SHA-256、字段映射、固定记录 ID、子集生成规则和子集文件 SHA-256 均记录在：

`data/dataset_manifest.json`

可使用以下脚本重新生成：

```text
python scripts/download_dataset.py
python scripts/audit_dataset.py
python scripts/build_fixed_subsets.py
```

## 5. 许可证义务

使用或重新分发这些教学子集时，应：

* 保留本说明文件；
* 保留 ASAP 数据集和论文的来源说明；
* 保留 Apache License 2.0 许可信息；
* 明确说明子集及字段经过修改；
* 不暗示本项目与美团、大众点评或原论文作者存在官方合作关系。

Apache License 2.0 的完整条款以 ASAP 官方仓库中的 `LICENSE` 文件为准。

## 6. 数据内容说明

ASAP 评论来源于真实用户评论。使用者应注意：

* 不将评论用于识别或追踪具体个人；
* 不公开评论中可能存在的个人联系方式；
* 教材截图应隐藏账号、姓名、路径和密钥等信息；
* 扩展或重新筛选子集时应进行人工隐私检查。

本说明不构成法律意见。使用者应根据自己的使用场景核验许可证及相关法律要求。
