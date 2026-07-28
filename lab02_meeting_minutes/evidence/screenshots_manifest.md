# 截图清单

## 隐私检查
- 截图不得显示 `.env`。
- 截图不得显示 API Key。
- 截图只展示虚构会议数据和运行结果。

## 截图
| 文件 | 输入 | 代码版本 | 模型 | 内容 | 隐私检查 |
|---|---|---|---|---|---|
| screenshots/streamlit_main_verified.png | meeting_main_001 | local workspace | deepseek-v4-flash | Streamlit 首页概览：完整模型名、输入、运行状态、Prompt、Schema、校验摘要 | 通过，未显示 `.env` 或 API Key |
| screenshots/streamlit_custom_input.png | 用户上传/粘贴文本 | local workspace | deepseek-v4-flash | Streamlit 上传/粘贴分析页：文件上传、文本粘贴、会议 ID、会议日期和真实模型触发按钮 | 通过，未显示 `.env` 或 API Key |
| screenshots/streamlit_structured_results.png | meeting_main_001 | local workspace | deepseek-v4-flash | Streamlit 结构化结果：行动项、决策、未决问题和当前 JSON 下载入口 | 通过，未显示 `.env` 或 API Key |
| screenshots/streamlit_addon_real_dataset.png | QMSum TS3010a | local workspace | deepseek-v4-flash | Streamlit 真实数据附加实验页：QMSum 输入、v2 结果、金标准对照和验收状态 | 通过，未显示 `.env` 或 API Key |
| screenshots/streamlit_qmsum_full_dataset.png | QMSum 本地完整数据集入口 | local workspace | deepseek-v4-flash | Streamlit 完整 QMSum 数据集区域：本地缓存目录、下载按钮和完整数据集选择边界说明 | 通过，未显示 `.env` 或 API Key |
| screenshots/streamlit_files_download.png | meeting_main_001 | local workspace | deepseek-v4-flash | Streamlit 文件下载页：回归报告、验收报告、事实包和用途说明 | 通过，未显示 `.env` 或 API Key |
