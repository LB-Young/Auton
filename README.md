# Auton

模块化的个人 Agent 工作台，包含任务执行、多 Agent 协作、轨迹评测、数据整理、通用训练和发布管理。后端以 Python 为主，前端使用 React。

## 快速启动

准备 Python、uv、Node.js 22（至少 22.14）、npm 和 Git。在项目根目录的 `.env` 中填写：

```dotenv
DEEPSEEK_API_KEY=你的实际密钥
```

然后执行：

```bash
make server
```

自动准备依赖、tokenizer 和本地判断资源，并使用预设真实任务配置启动。首次需要联网下载约 700 MB 模型/tokenizer 资源（另需安装依赖），后续复用已校验文件；不自动训练或调用付费验收。

打开 [工作台](http://127.0.0.1:5173)，`Ctrl+C` 停止。没有 `.env` 时首次执行会创建模板，填写 key 后重试即可。

打开页面即可开始多轮对话，输入框旁选择远程或本地模型，也可选择本地项目目录，右侧工作面板按需展开。详见 [对话工作区](docs/conversation-workspace.md)；手动开发启动与环境要求见 [快速启动](docs/quickstart.md)。

## 文档

- [快速启动与常见问题](docs/quickstart.md)
- [全部功能与使用流程](docs/usage.md)
- [配置说明与完整参数](docs/configuration.md)
- [API、CLI 与请求参数](docs/api.md)
- [开发、测试与清理](docs/development.md)
- [完整文档目录](docs/README.md)

训练和后台调度默认关闭，训练流程面向最终部署环境；候选上线需要独立评测和用户批准。
