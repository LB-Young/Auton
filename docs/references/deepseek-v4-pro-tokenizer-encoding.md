# DeepSeek V4 Pro：协议完整性与精确计数笔记

整理日期：2026-11-18。本文为理解笔记，原始资料见链接。

原链接：[官方编码说明](https://huggingface.co/deepseek-ai/DeepSeek-V4-Pro/blob/b5968e9190ef611bbf34a7229255be88a0e937c1/encoding/README.md)、[官方编码实现](https://huggingface.co/deepseek-ai/DeepSeek-V4-Pro/blob/b5968e9190ef611bbf34a7229255be88a0e937c1/encoding/encoding_dsv4.py)、[tokenizer](https://huggingface.co/deepseek-ai/DeepSeek-V4-Pro/blob/b5968e9190ef611bbf34a7229255be88a0e937c1/tokenizer.json)。

## 我的理解

上下文是协议结构。assistant 的工具请求和对应的 tool 响应互相约束；截取若干条尾部消息，可能把真实结果变成孤立响应，也可能留下永远得不到结果的请求。压缩策略应先验证原始历史，再按完整用户轮次移除；发现未决调用时由运行时完成对账，不能用截断隐藏问题。

Pro V4 的编码实现支持会话与工具表达，但其模板身份需要独立固定。模型切换后不能沿用旧模型算出的预算；应基于原始状态重新装配并计数。

## Auton 中的应用

M08 给 Pro 单独固定 commit、tokenizer 和编码模块，保留本地编码版本。目标、边界、账本校验后的 receipt 摘要与最新用户轮次始终保留；放不下就阻塞。压缩只影响此次模型视图，不覆盖原历史或持久 checkpoint。

当前重排是可复现的词项/中文 bigram 基线，未启用 Jev 或 Laya 自动决策，也未把历史交给模型生成语义摘要。检索结果保留不可信标记、内容摘要和每份来源的字符区间；资料不能变成系统权限。

本地测试工具历史包含 schema、调用参数及响应，计数为 347；真实装配后的短文本样例本地与远端均为 212。后续不同格式或云端别名变化仍以响应 usage 为准。
