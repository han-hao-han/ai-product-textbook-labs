# 控制终态消息守卫（v9）

预测或自动补货问题必须返回既定 `boundary`。`message` 只说明当前数据与工具不支持预测和自动补货，不得含任何数字或日期，也不得把 `supported_alternative` 复制进 `message`。`supported_alternative` 仍必须精确为 `"展示历史月度销售趋势并标记2011-12不完整"`，且 `boundary_codes` 必须精确包含 `forecasting_unsupported`、`automatic_replenishment_unsupported`。
