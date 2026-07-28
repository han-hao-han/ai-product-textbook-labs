# 附加实验数据分发策略

## 默认策略

附加实验默认不提交完整 QMSum 数据集。仓库只保留三份经过 H2 审计的转换样例，用于演示和小规模回归：

- `data/selected_cases/TS3010a.md`：主案例，带小规模人工金标准；
- `data/selected_cases/IS1003a.md`：仓库内探索样例，不做 gold 验收；
- `data/selected_cases/ES2011a.md`：仓库内探索样例，不做 gold 验收。

完整 QMSum 数据集由用户在 Streamlit 界面中自行选择下载。下载结果只写入本地忽略目录 `data/downloads/qmsum_full/`，不纳入 Git。

## 允许提交

- 数据来源审计文档；
- 许可和引用说明；
- 三个审计样例的转换输入；
- 三个审计样例的 manifest；
- TS3010a 的小规模人工金标准；
- 小规模派生结果；
- 自动验收报告；
- 不含密钥、不含 `.env`、不含大段真实会议原文的截图。

## 不提交

- 完整 QMSum 原始数据集；
- Streamlit 运行时从完整数据集临时转换的输入；
- 用户上传或粘贴的会议文本；
- 未确认许可的原始数据副本；
- 未脱敏的敏感个人信息；
- 真实 API Key 或本地 `.env`。

## 本地完整数据集目录

Streamlit 下载入口使用以下本地缓存目录：

```text
addon_real_dataset/
├─ data/
│  ├─ selected_cases/
│  ├─ manifests/
│  ├─ gold/
│  └─ downloads/
│     └─ qmsum_full/     # 本地缓存，Git 忽略
├─ outputs/
│  └─ streamlit_runs/    # 用户运行输出，Git 忽略
├─ evidence/
└─ scripts/
```

用户从完整数据集中选择样例后，系统只把该样例转换为本次运行输入并调用现有链路。除 TS3010a 外，没有人工金标准，因此只能做结构校验、证据校验和人工查看，不能做严格 gold 验收。
