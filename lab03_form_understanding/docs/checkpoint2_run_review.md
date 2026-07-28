# 检查点2运行核验

## 当前状态

```text
检查点2正式运行：已由用户主动完成
技术一致性核验：通过
检查点2人工确认：已通过
字段内容正确性：尚未比较
检查点3：尚未开始
```

## 运行事实

| 项目 | 实际结果 |
|---|---|
| 样本 | `zh_train_103` |
| run_id | `20260722T173933_965242Z` |
| 运行时间 | `2026-07-22T17:39:33.965768+00:00` |
| 固定模型 | `qwen3.7-plus-2026-05-26` |
| Prompt | `v1` |
| Schema | `v1` |
| finish_reason | `stop` |
| 耗时 | `17.01`秒 |
| fields | 28 |
| warnings | 0 |
| usage | 已保存API真实返回值 |
| 本次失败记录 | 0 |

## 保存一致性

本次运行生成：

```text
results/history/raw/zh_train_103_20260722T173933_965242Z.json
results/history/parsed/zh_train_103_20260722T173933_965242Z.json
results/current/zh_train_103.json
```

核验结果：

- raw中的模型JSON与parsed结果一致；
- parsed历史与current结果一致；
- 这是独立于H3核验的新运行；
- 未发现API Key字段或内容；
- 未发现Authorization、Bearer、Cookie或完整请求头。

完整运行文件只保存在本地，不提交仓库。本文件不保存模型识别出的具体字段值。

## 读者应理解

```text
真实调用成功
≠ JSON解析成功
≠ Schema校验成功
≠ 字段内容正确
```

本次前三项已通过。字段内容是否正确必须在检查点3由程序与人工标注参考结果进行确定性比较。
