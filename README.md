# Auton

模块化的个人 Agent 工作台，包含任务执行、多 Agent 协作、轨迹评测、数据整理、通用训练和发布管理。后端以 Python 为主，前端使用 React。

## 快速启动

准备 Python 3.12、uv、Node.js 22（至少 22.14）、npm 11.8 和 Git，在项目根目录执行：

```bash
make setup
make dev
```

打开 [工作台](http://127.0.0.1:5173)。后端地址为 `http://127.0.0.1:8000`，`Ctrl+C` 停止服务。

仅体验界面可进入 [演示对话](http://127.0.0.1:5173/?view=chat)，不需要模型 key。运行真实任务前，还需配置 DeepSeek key、tokenizer 和本地判断资源，见 [真实任务启动步骤](docs/quickstart.md#真实任务启动)。

## 文档

- [快速启动与常见问题](docs/quickstart.md)
- [全部功能与使用流程](docs/usage.md)
- [配置说明与完整参数](docs/configuration.md)
- [API、CLI 与请求参数](docs/api.md)
- [开发、测试与清理](docs/development.md)
- [完整文档目录](docs/README.md)

训练和后台调度默认关闭，训练流程面向最终部署环境；候选上线需要独立评测和用户批准。
