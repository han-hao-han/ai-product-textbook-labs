# H2 样例候选：QMSum Product 域

## 候选原则

附加实验目标是验证现有链路在真实会议转写上的适配边界，因此候选样例应满足：

- 来源明确，来自 QMSum 官方仓库；
- 优先 Product 域，贴近主实验的产品会议场景；
- 规模适中，便于人工金标准准备；
- 不默认提交完整原始会议转写；
- 能体现真实会议的口语化、多人轮次和结构噪声。

## 候选 A：TS3010a

| 项目 | 内容 |
|---|---|
| 数据集 | QMSum |
| 域 | Product |
| 划分 | val |
| 官方路径 | data/Product/val/TS3010a.json |
| 文件大小 | 24,793 bytes |
| 发言轮次 | 168 |
| 主题数 | 3 |
| general queries | 1 |
| specific queries | 2 |
| 推荐用途 | 附加实验主案例 |

### 推荐理由

- Product 域与 1.5.2 主实验“产品会议纪要”目标最接近。
- 文件较短，适合先做小规模真实数据验证。
- QMSum 原始结构包含 `meeting_transcripts`，可以转换为当前 CLI/Streamlit 已支持的会议转写文本。
- 样例中说话人是角色类标识，适合作为教材附加实验，不需要展示真实个人姓名。

### 风险

- QMSum 的任务目标是 query-based meeting summarization，不是行动项、决策、未决问题抽取；人工金标准需要单独制作。
- 真实会议可能没有清晰行动项或决策，验收标准应允许“低密度抽取”，不能强行要求像虚构样例一样完整。
- 不应把完整原文直接纳入教材正文或截图。

## 备选 B：IS1003a

| 项目 | 内容 |
|---|---|
| 数据集 | QMSum |
| 域 | Product |
| 划分 | test |
| 官方路径 | data/Product/test/IS1003a.json |
| 文件大小 | 41,427 bytes |
| 推荐用途 | 后续回归样例 |

## 备选 C：ES2011a

| 项目 | 内容 |
|---|---|
| 数据集 | QMSum |
| 域 | Product |
| 划分 | test |
| 官方路径 | data/Product/test/ES2011a.json |
| 文件大小 | 45,255 bytes |
| 推荐用途 | 后续对照样例 |

## H2 当前选择

用户已确认选择候选 A `TS3010a` 作为真实数据集附加实验主案例，并允许读取该样例原文、转换为本实验输入格式、继续制作小规模人工金标准，但不提交完整 QMSum 数据集。

已生成：

- 转换输入：`data/selected_cases/TS3010a.md`
- 样例清单：`data/manifests/TS3010a_manifest.json`
- 金标准草案：`data/gold/TS3010a_gold.json`

后续根据界面需求，仓库内额外保留两个候选样例的转换输入和 manifest，作为探索性分析入口，不改变 H2 主案例和金标准结论：

- `data/selected_cases/IS1003a.md`
- `data/manifests/IS1003a_manifest.json`
- `data/selected_cases/ES2011a.md`
- `data/manifests/ES2011a_manifest.json`

完整 QMSum 数据集仍不提交仓库；用户可在 Streamlit 中自行下载到本地忽略缓存并选择任意样例分析。

## 下一步建议

H2 金标准草案确认后再执行：

1. 复用或调整当前实验 Schema/Prompt/校验器；
2. 跑 Mock 或转换链路检查；
3. 选择是否做 1 次真实模型 Smoke Test；
4. 标明这是 QMSum 真实会议附加实验，不替代主实验 accepted 结论。
