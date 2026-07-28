# 检查点1报告：文档、清洗与Chunk

## 状态

```text
warning
```

## 固定来源

- Repository：https://github.com/fastapi/fastapi
- Release：0.136.3
- Commit：82064857539e6286522c347b4b11331b48dd2378
- License：MIT

## 文档审计

- 候选Markdown：105
- 纳入Markdown：102
- 排除Markdown：3
- 代码引用：420
- 唯一代码依赖：268
- 依赖范围：{'approved_exception': 1, 'code_source_root': 419}
- 已批准依赖例外：1
- 缺失代码依赖：0
- 缺失内部链接：1

## 清洗与Chunk

- 清洗文档：102
- Chunk：400
- Chunk策略：heading_aware_adjacent_merge_v1
- 含代码Chunk：322
- 含表格Chunk：1
- 合并多个相关小节的Chunk：347
- 含Overlap的Chunk：143
- 位于500～800目标区间：322
- 目标区间占比：0.805
- 低于目标下限：59
- 低于下限原因：{'document_tail': 48, 'next_block_would_exceed_target_max': 5, 'short_document': 6}
- 超过目标上限：19
- 超过上限原因：{'oversized_atomic_code_block': 19}
- 长度分位数：{'min': 112, 'p10': 421, 'p25': 585, 'median': 745, 'p75': 783, 'p90': 797, 'max': 2114}
- 长度区间分布：{'0_49': 0, '50_99': 0, '100_199': 8, '200_299': 10, '300_399': 16, '400_499': 25, '500_800': 322, '801_plus': 19}
- Token计数方法：deterministic_cjk_ascii_estimate_v1
- 语料哈希：71cf57bca05ddbc43a61a6155690f5bd4ebc07cc1cf6f181fe80bfc2d66e741d

## 错误

- 无

## 读者应该观察什么

- 纳入页面是否严格为H1确认的102页；
- 三个外围页面是否被明确排除；
- docs_src代码依赖是否全部存在并展开；
- 唯一批准的fastapi/openapi/docs.py例外是否精确出现一次；
- 代码块和表格是否保持完整；
- 相邻相关短小节是否合并，正文中是否保留必要标题；
- 每个Chunk是否带有Commit、源路径、全部章节路径和哈希；
- Overlap是否只来自同一章节；
- 过短或超长Chunk是否带有明确原因。

## 真实性声明

本检查点未调用Embedding模型、在线生成模型或Codex Judge，也未产生真实检索、回答或评价结果。
