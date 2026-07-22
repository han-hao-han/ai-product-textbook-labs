# 已验证环境

## Python 环境
- conda 环境：research_env
- Python：3.10.20
- pytest：9.1.1
- pydantic：2.13.4
- streamlit：1.59.2

## 模型配置
- Base URL：https://api.deepseek.com
- 模型：deepseek-v4-flash
- API Key：只从 `.env` 读取，未写入代码、报告或截图。

## 本地检查
- 单元测试：22 passed，1 pytest cache warning。
- Mock 固定回归：15 cases，ok=true。
- 代表真实回归：4 cases，ok=true。
- H4 验收脚本框架：已实现。
