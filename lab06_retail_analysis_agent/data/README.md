# UCI Online Retail 数据说明

## 数据身份

- 数据集：Online Retail
- UCI 数据集 ID：352
- 创建者：Daqing Chen
- DOI：<https://doi.org/10.24432/C5BW33>
- 官方页面：<https://archive.ics.uci.edu/dataset/352/online+retail>
- 官方下载：<https://archive.ics.uci.edu/static/public/352/online%2Bretail.zip>
- 许可：Creative Commons Attribution 4.0 International（CC BY 4.0）
- 许可全文：<https://creativecommons.org/licenses/by/4.0/>

UCI 官方页面说明该数据集包含英国一家非实体店在线零售商在
2010-12-01 至 2011-12-09 期间的交易记录。

## 许可与署名

CC BY 4.0 允许复制、重新分发和改编，但必须：

1. 给出适当署名；
2. 提供许可证链接；
3. 说明是否修改了数据；
4. 不暗示原作者或 UCI 为本实验背书。

建议署名：

> Chen, D. (2015). Online Retail [Dataset]. UCI Machine Learning Repository.
> https://doi.org/10.24432/C5BW33. Licensed under CC BY 4.0.

## 仓库边界

原始文件和本地审计结果不提交 Git：

```text
data/
├─ downloads/
│  └─ online_retail.zip
└─ raw/
   ├─ Online Retail.xlsx
   ├─ download_metadata.json
   └─ audit_report.json
```

仓库只保留下载、审计代码和本说明。

公开示例只展示聚合客户指标，不直接展示原始 `CustomerID`。

首次从官方来源成功下载后，已将固定原始工作簿的大小和 SHA-256
记录在 `source_manifest.json`。下载脚本会校验工作簿哈希，避免来源文件
发生未说明变化后仍被静默当作同一份固定数据。

## 下载

在 `lab06_retail_analysis_agent/` 目录运行：

```powershell
python scripts/download_online_retail.py
```

脚本会：

1. 只从 UCI 官方地址下载 ZIP；
2. 只解压 ZIP 中名为 `Online Retail.xlsx` 的文件；
3. 计算 ZIP 和 XLSX 的 SHA-256；
4. 校验 XLSX 与固定数据清单一致；
5. 将来源、下载时间、文件大小和哈希写入本地元数据。

重复运行时默认复用已有文件。只有用户明确执行 `--force` 时才重新下载并覆盖。

## 数据审计

数据审计依赖仍是 H3 前的开发范围，尚未冻结最终版本：

```powershell
python -m pip install -r requirements-data.txt
python scripts/inspect_online_retail.py
```

审计只统计事实，不提前把负数量解释为退货，也不提前冻结销售额口径。

重点检查：

- 实际字段和工作表；
- 缺失值；
- 取消前缀的大小写；
- 正数、零和负数量；
- 正价、零价和负价；
- 取消标记与数量符号的交叉关系；
- 日期解析与时间范围；
- 唯一订单、商品、客户和国家数量；
- 重复行。

`audit_report.json` 不保存原始 `CustomerID` 值。

## H2 清洗候选剖析

在冻结清洗规则前运行：

```powershell
python scripts/profile_cleaning_candidates.py
```

输出：

```text
data/raw/cleaning_profile.json
```

清洗与指标口径经人工冻结后，机器可读契约保存在：

```text
config/h2_metric_contract.json
```

该契约记录冻结状态、分层数据范围、互斥分类、指标公式、时间与舍入口径、
真实数据基线和变更控制。清洗、指标和固定验证问题均冻结后，
`h2_overall` 为 `frozen`。

按冻结口径生成固定问题的本地参考答案：

```powershell
python scripts/build_h2_reference_answers.py
```

结果保存到 `data/raw/h2_reference_answers.json`。该文件仅包含聚合结果，
不输出 CustomerID 明细，并与原始数据一起保持在本地。

10个已冻结的固定验证问题定义保存在：

```text
config/h2_validation_questions.json
```

具体白名单工具名称和参数 Schema 仍属于 H3，
不在 H2 固定问题中提前冻结。冻结内容如需调整，必须重新提交人工确认。

该文件只保存聚合证据，不保存原始 `CustomerID`。它会展示：

- 互斥的候选记录分类；
- 非 `C` 前缀负数量的商品与描述分布；
- 零价和负价记录；
- 缺失商品描述的交叉关系；
- 正常销售候选中的客户覆盖率；
- 完全重复行去除前后的敏感性；
- 商品编号与名称的一致性；
- 发票内客户和国家的一致性；
- 单价实际小数位数。

其中的 `Quantity × UnitPrice` 仅是帮助比较规则影响的机械诊断值，
不是已经冻结的销售额。脚本不会生成清洗后数据。
