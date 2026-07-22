# 教材候选代码片段

## Schema 校验
- `src/schemas.py`：定义行动项、决策、未决问题和处理元数据。

## 证据校验
- `src/validators.py`：校验 evidence 是否能在原文定位；定位时容忍真实转写噪声标记和空白差异，同时校验负责人是否在说话人中。

## 日期规范化
- `src/date_normalizer.py`：根据会议日期规范化“本周五”“下周三”等相对日期。

## 主金标准对照
- `src/gold_compare.py`：对比 action_items、decisions、open_questions 的召回和过抽。

## 证据修复
- `src/evidence_repair.py`：先修复可映射回原文连续片段的 evidence 差异；对 QMSum 类噪声转写，可保守回退到最匹配的一整条原文发言行。
