# 附加实验已知限制

- 已做严格金标准验收的真实样例只有 QMSum Product/val/TS3010a。
- TS3010a 的严格金标准验收基于 v2 产品设计要求召回 Prompt；当前 Streamlit 探索链路已切换到 v4 通用 Prompt，尚未重新做 v4 gold 验收。
- 仓库内额外保留 IS1003a、ES2011a 两个转换样例，但它们没有人工金标准，只适合探索性结构化分析。
- 用户可在 Streamlit 中下载完整 QMSum 到本地缓存并选择任意样例分析，但这些样例默认没有 gold 验收。
- QMSum 原任务是 query-based meeting summarization，不是行动项、决策和未决问题抽取。
- QMSum 英文真实会议转写包含 `{vocalsound}`、`{gap}`、`{disfmarker}` 等噪声。
- v2 真实结果仍需要确定性 evidence 修复；当前校验器会容忍 `{vocalsound}`、`{gap}`、`{disfmarker}` 等噪声标记，修复器会优先映射回原文片段，必要时回退到最匹配的一整条原文发言行。
- TS3010a 金标准中的 decisions 更接近“被接受的产品设计要求”，不是正式项目决议。
- 结果不能外推为完整 QMSum 数据集性能。
