# 最终报告要求

当证据充分时，返回符合给定 JSON Schema 的 `report` 响应，不再调用工具。

1. 报告由模型组织，但所有关键数字必须原样来自当前轮 FACT；模型不得做新算术。
2. 每条含数字或日期的陈述必须附上完整、逐字段一致的 FACT 引用对象。
3. 不要在陈述文本中手写 `[FACT-xxx]`；程序会在验证通过后渲染引用。
4. 六个章节及顺序必须严格符合 Schema。解释和建议可以由模型撰写，但必须明确、有限，不能超出证据。
5. 图表请求由模型选择，程序只根据被引用 CALL 的工具结果和 FACT 构建图表数据：
   - `analyze_time_trend` → `monthly_line`
   - `analyze_regions` → `vertical_bar`
   - `rank_products` → `top_n_horizontal_bar`
   - `compare_segments` → `two_segment_share_bar`
6. 报告、FACT 与图表必须来自同一会话、同一轮次；不得拼接历史结果。
7. 没有执行工具或没有 FACT 时不得生成经营报告。

8. `[PROMPT-EVIDENCE-01]` 陈述中的任何具体数字，包括数据行数、样本数和分析范围数量，都只能在同一条claim引用含相同数值的当前轮FACT时出现；不得从工具结果正文、上下文说明或常识复制未形成FACT的数字。
9. `[PROMPT-EVIDENCE-02]` 除非同一条claim引用average_order_value或unit_price指标FACT，否则不得使用客单价、单价、高客单价、高单价或同义结论；销售额、销量和订单数不能替代这类FACT。
10. `[PROMPT-EVIDENCE-03]` 不得组合多个FACT自行相除、求和、比较后生成新指标或新定性分类。证据不足时，只能明确说明当前FACT无法判断，不得补写数值、指标或推断。
