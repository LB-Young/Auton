# Auton 文档

| 想做什么 | 阅读 |
| --- | --- |
| 安装并启动 | [快速启动](quickstart.md) |
| 按页面使用全部功能 | [功能与使用指南](usage.md) |
| 配置模块、密钥、预算与目录 | [配置指南](configuration.md) / [所有配置字段](reference/configuration.md) |
| 使用 HTTP、WebSocket 和 CLI | [API/CLI 指南](api.md) / [HTTP 路由目录](reference/api-endpoints.md) / [全部请求响应字段](reference/api-schemas.md) |
| 开发、检查、验收和清理 | [开发维护](development.md) |
| 部署本地执行模型、批准上线和回滚 | [本地运行时与发布](local-runtime-and-release.md) |
| 配置后台任务、监控、备份和恢复 | [后台运行](background-operations.md) |
| 理解模块架构、阶段与实际验收范围 | [里程碑总表](milestones/README.md) / [工厂规范](milestones/module-factory-contract.md) |
| 理解决策学习和模型效果门槛 | [Jev 决策学习](jev-decision-learning.md) / [决策模型评估发布](decision-model-evaluation-and-release.md) |

使用文档描述当前代码行为；设计文档和历史里程碑保留研究背景与当时证据，不代表默认启用所有能力。参数参考由 `scripts/export_user_docs.py` 从代码默认值和已提交的 OpenAPI 契约生成，可用 `--check` 验证。
