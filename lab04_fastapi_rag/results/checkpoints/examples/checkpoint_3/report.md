# 检查点3报告：完整RAG问答

## 状态

```text
passed
```

## 三类读者体验

### 知识库内

- 问题：如何使用Pydantic模型声明请求体？
- 最终状态：`answered`
- Top k：5
- 总耗时：22.498355秒
- 保存结果：`interactive/saved/result_001/result.json`

### 边界

- 问题：我的8核16GB服务器在每秒5000请求时应该精确启动多少个Uvicorn worker？
- 最终状态：`model_refused`
- Top k：5
- 总耗时：7.877064秒
- 保存结果：`interactive/saved/result_002/result.json`

### 知识库外

- 问题：明天北京天气如何？
- 最终状态：`retrieval_rejected`
- Top k：5
- 总耗时：3.318672秒
- 保存结果：`interactive/saved/result_003/result.json`

## 读者应该观察什么

- Top 1门控拒答不会调用在线模型；
- 门控通过后模型仍可因证据不足返回model_refused；
- answered必须通过Schema、引用集合和Markdown安全校验；
- 模型只看到重排后的证据，不看到分数、排名或阈值；

## 真实性声明

本报告只汇总用户显式保存的三类现场体验结果；未运行30道正式题，未调用Codex Judge。
