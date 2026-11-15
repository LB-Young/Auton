# Agent 执行与构建博客：逐篇中文阅读笔记

整理日期：2026-11-15。共 35 篇来源，每篇都有独立 Markdown 笔记，直接放在 `references/` 目录下。

这些文件采用与既有参考资料一致的形式：来源信息、核心观点、机制、个人理解、对 Auton 的启示、局限和建议验证。正文是中文概括和分析，不是原文下载、逐段翻译或全文转载。原文链接用于追溯；不是只有链接的占位文件。

来源观点与个人推论分开；建议验证尚未执行。历史文章中的产品能力、模型和实验结果只按当时语境理解，不作为今天默认配置的保证。对公开案例没有独立审计，也未逐篇复现实验。

关联文档：[执行问题与解决方案手册](../agent-execution-problems-and-solutions.md) · [构建者案例文档](../agent-builder-case-studies.md)。机器可读对应关系：[阅读笔记 manifest](./agent-article-reading-manifest.json)。

## 逐篇目录

| 编号 | 中文阅读笔记 | 来源信息 | 引用位置 |
|---|---|---|---|
| REF001 | [AWS：Deep Insight 的五类生产问题](./aws-deep-insight-production-challenges.md) | AWS Solutions Architecture；发布日期本次未固定 | 问题手册 |
| REF002 | [AWS：超时、重试、退避与抖动](./aws-timeouts-retries-backoff-jitter.md) | AWS Builders’ Library，Marc Brooker；2019-12-05 | 问题手册 |
| REF003 | [Cognition：为什么不要默认构建多 Agent](./cognition-dont-build-multi-agents.md) | Cognition，Walden Yan；2025-06-12 | 问题手册 |
| REF004 | [Cognition：哪些多 Agent 模式实际有效](./cognition-multi-agents-working.md) | Cognition，Walden Yan；2026-04-22 | 问题手册 |
| REF005 | [Cursor：长运行编码 Agent 的扩展经验](./cursor-scaling-long-running-agents.md) | Cursor，Wilson Lin；2026-01-14 | 问题手册 |
| REF006 | [Cursor：走向自动运行代码库的取舍](./cursor-self-driving-codebases.md) | Cursor，Wilson Lin；2026-02-05 | 问题手册 |
| REF007 | [Simon Willison：Agent 数据外泄的危险组合](./simon-willison-lethal-trifecta.md) | Simon Willison；2025-06-16 | 问题手册 |
| REF008 | [Temporal：持久执行为什么仍需要幂等](./temporal-idempotency-durable-execution.md) | Temporal，Keith Tenzer、Joshua Smith；2024-02-27 | 问题手册 |
| REF009 | [Anthropic：用沙箱减少逐次许可提示](./anthropic-claude-code-sandboxing.md) | Anthropic Engineering；2025-10-20 | 问题手册 |
| REF010 | [Anthropic：通过代码执行提高 MCP 使用效率](./anthropic-code-execution-with-mcp.md) | Anthropic Engineering；2025-11-04 | 问题手册 |
| REF011 | [Anthropic：理解 Agent 评测的基本对象](./anthropic-demystifying-agent-evals.md) | Anthropic Engineering；2026-01-09 | 问题手册 |
| REF012 | [Anthropic：有效上下文工程](./anthropic-effective-context-engineering.md) | Anthropic Engineering；2025-09-29 | 问题手册 |
| REF013 | [Anthropic：长运行 Agent 的执行框架](./anthropic-effective-long-running-harnesses.md) | Anthropic Engineering；2025-11-26 | 问题手册 |
| REF014 | [Anthropic：编码评测中的基础设施噪声](./anthropic-infrastructure-noise.md) | Anthropic Engineering；2026-02-05 | 问题手册 |
| REF015 | [Anthropic：多 Agent 研究系统的构建经验](./anthropic-multi-agent-research-system.md) | Anthropic Engineering；2025-06-13 | 问题手册 |
| REF016 | [Anthropic：为 Agent 设计有效工具](./anthropic-writing-effective-tools.md) | Anthropic Engineering；2025-09-11 | 问题手册 |
| REF017 | [Drew Breunig：长上下文如何失败](./drew-breunig-how-long-contexts-fail.md) | Drew Breunig；2025-06-22 | 问题手册 |
| REF018 | [LangChain：从第一原则设计 Agent Runtime](./langchain-building-langgraph.md) | LangChain，Nuno Campos；2025-09-04 | 问题手册 |
| REF019 | [LangChain：常驻 Agent 带来的新上下文问题](./langchain-context-challenges-late-2026.md) | LangChain，Harrison Chase；2026-11-02 | 问题手册 |
| REF020 | [LangChain：写入、选择、压缩与隔离](./langchain-context-engineering.md) | LangChain；2025-07-02 | 问题手册 |
| REF021 | [LangChain：Agent Builder 的文件式记忆](./langchain-agent-builder-memory.md) | LangChain；2026-02-21 | 问题手册 |
| REF022 | [LangChain：多 Agent 的上下文模式](./langchain-multi-agent-context-modes.md) | LangChain，Thushanth Bengre、Chester Curme；2026-09-08 | 问题手册 |
| REF023 | [LangChain：在后台运行子 Agent](./langchain-background-subagents.md) | LangChain，Hunter Lovell、Colin Francis；2026-04-16 | 问题手册 |
| REF024 | [Cloudflare：把 MCP 工具转成代码 API](./cloudflare-code-mode.md) | Cloudflare，Kenton Varda、Sunil Pai；2025-09-26 | 案例文档 |
| REF025 | [Parcha / Grep：三年 Agent 架构迭代与静默事故](./parcha-grep-three-years-agent-lessons.md) | AJ Asver；2026-09-10 | 案例文档 |
| REF026 | [Braintrust × Vercel：检验 bash 是否足够](./braintrust-vercel-bash-evaluation.md) | Braintrust / Vercel，Ankur Goyal 等；2026-01-22 | 案例文档 |
| REF027 | [Vercel：删减 d0 的专用工具](./vercel-remove-agent-tools.md) | Vercel，Andrew Qu；2025-12-22 | 案例文档 |
| REF028 | [Anthropic：Claude Code 质量退化复盘](./anthropic-claude-code-quality-postmortem.md) | Anthropic Engineering；2026-04-23 | 案例文档 |
| REF029 | [Anthropic：并行 Agent 构建 C 编译器](./anthropic-parallel-c-compiler.md) | Anthropic，Nicholas Carlini；2026-02-05 | 案例文档 |
| REF030 | [Anthropic：长应用任务中的规划、生成与评估](./anthropic-long-running-app-harness.md) | Anthropic，Prithvi Rajasekaran；2026-03-24 | 案例文档 |
| REF031 | [Anthropic：分离 session、harness 与 sandbox](./anthropic-managed-agent-architecture.md) | Anthropic Engineering；2026-04-08 | 案例文档 |
| REF032 | [Anthropic：Project Vend 第一阶段的失败](./anthropic-project-vend-phase-one.md) | Anthropic / Andon Labs；2025-06-27 | 案例文档 |
| REF033 | [Anthropic：Project Vend 第二阶段的改进与剩余风险](./anthropic-project-vend-phase-two.md) | Anthropic / Andon Labs；2025-12-18 | 案例文档 |
| REF034 | [Manus：构建 Agent 的上下文工程经验](./manus-context-engineering-lessons.md) | Manus，Yichao “Peak” Ji；2025-07-18 | 案例文档 |
| REF035 | [Uber：Finch 的路由、数据查询与验证](./uber-finch-data-agent.md) | Uber Engineering；2025-07-17 | 案例文档 |

## 推荐串读

- 多 Agent 是否值得：Cognition 两篇 → Cursor 两篇 → Anthropic 编译器团队。比较上下文、写入所有权与问题可分解性。
- 工具抽象怎么选：Vercel 删工具 → Braintrust/Vercel 评测 → Cloudflare Code Mode。避免把某种抽象当万能答案。
- 长任务怎么稳定：长运行 harness → Managed Agents → 质量退化复盘。区分会话状态、执行环境与模型配置。
- 结果是否可信：Parcha/Grep 静默事故 → Finch → Agent evals → infrastructure noise。分别检查业务覆盖、路由、评分和环境。

## 整理方式变更

此前误按“原文归档”处理，生成了 1 篇英文原文和 34 篇未归档状态。这不符合本项目参考目录的阅读笔记用途。现已全部整理为中文 Markdown 笔记，替换英文全文，并移除原文归档索引与状态 manifest；不再把原文转载许可作为编写自己理解的笔记的阻塞条件。
