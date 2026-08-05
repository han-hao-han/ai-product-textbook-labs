# 工具参数 JSON 守卫（v7）

每个工具的 `arguments` 必须是合法 JSON 对象；所有字符串都必须带双引号。调用 `analyze_customers` 分析全部数据时，参数必须逐字采用：`{"period":"all_data","start_date":"__NONE__","end_date":"__NONE__","include_coverage":true}`。`__NONE__` 是字符串，不是变量或 JSON 关键字，绝不能省略双引号。
