# 当前轮报告生成规则

当且仅当当前轮工具结果已经足以回答用户问题时，返回 `response_type=report` 的单一 JSON 对象。不要调用新工具，不要添加 Markdown 代码围栏。

报告对象必须满足程序给出的 ReportDraft JSON Schema，并遵守以下规则：

1. `session_id`、`turn_id`必须与当前轮一致。
2. 六个章节必须完整并严格按以下顺序：
   - 用户问题与分析口径
   - 关键经营发现
   - 工具证据与图表
   - 有限解释
   - 经营建议
   - 数据与分析限制
3. 每个数值、日期、月份、比例和排名只能来自当前轮 FACT。
4. 使用某个 FACT 时，`evidence`必须逐字段原样复制该 FACT 的 `fact_id`、`value`、`display_value`、`unit`、`rank`及分析范围。
5. 不得在 `statement` 中自行写 `[FACT-...]`；引用标记由程序校验后添加。
6. 不得自行做算术、生成新比例或改变显示精度。
7. “有限解释”和“经营建议”必须明确是基于现有描述性数据的有限判断，不得写成因果结论、利润结论、预测或自动决策。
8. 若不需要图表，`chart_requests`返回空数组。若需要图表，只能从下列映射中选择，并引用对应内部 CALL：
   - `analyze_time_trend` → `monthly_line`
   - `analyze_regions` → `vertical_bar`
   - `rank_products` → `top_n_horizontal_bar`
   - `compare_segments` → `two_segment_share_bar`
9. 每个图表必须完全来自同一个 CALL 的 FACT；不得拼接不同 CALL。
10. content必须直接以`{`开始并以`}`结束；不要在JSON前后写说明，不要使用Markdown代码围栏。
11. 日期和月份必须沿用FACT中的ISO格式，例如`2011-11`；不得改写成“2011年11月”。
12. 一条陈述提到几个数值，就必须在该条`evidence`中分别提供支持这些数值的全部FACT；不得只引用其中一个。
13. 不要在陈述中书写`CALL-001`等内部调用编号；程序已通过evidence保存追溯关系。
14. 用户问题中的Top N、日期或其他数值若出现在报告陈述中，也必须引用对应FACT；否则改用不含该数值的文字。
15. 不得根据月份或商品名称推断季节性、备货行为、利润、需求原因或因果关系；不得提出包含新月份、补货量或预测值的建议。

返回结构：

```json
{
  "response_type": "report",
  "report": {
    "schema_version": "1.5.6-h3-report-draft-v1",
    "session_id": "由程序提供",
    "turn_id": "由程序提供",
    "title": "简洁标题",
    "sections": []
  },
  "chart_requests": [
    {
      "call_id": "CALL-001",
      "chart_type": "monthly_line",
      "title": "图表标题"
    }
  ]
}
```
