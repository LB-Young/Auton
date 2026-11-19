# 快速启动

## 环境准备

在克隆后的 Auton 根目录执行命令。当前依赖基线：Python 3.12、uv、Node.js 22.14.0（22.x）、npm 11.8.0、Git；版本文件为 `.python-version`、`.node-version` 和 `clients/web/package.json`。Python/Node 依赖分别由 uv.lock/package-lock.json 固定。项目使用 POSIX 文件锁与受控目录；完整运行使用 Linux/macOS，Windows 可在 Linux 环境中运行。

## 先启动界面

```bash
make setup
make dev
```

`make setup` 执行 `uv sync --frozen` 和 `npm ci`。默认安装核心应用与开发依赖，不安装训练环境，也不下载执行模型权重。

- 前端：[http://127.0.0.1:5173](http://127.0.0.1:5173)。默认首页是任务工作台。
- 无 key 演示：[演示对话](http://127.0.0.1:5173/?view=chat)，仅合成数据。
- 后端健康：[http://127.0.0.1:8000/api/v1/health](http://127.0.0.1:8000/api/v1/health)。
- API 类型查看：[http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)。写请求还需要身份与自定义头，见 [API 指南](api.md)。

Ctrl+C 停止本次启动的服务。打开网页不代表真实模型资源已经齐备；缺少 key/tokenizer/判断权重时，任务会显示不可用或阻塞。

## 真实任务启动

1. 在项目根目录创建 `.env`，填写 `DEEPSEEK_API_KEY`。仅首次创建时执行复制命令，已有文件不要覆盖：

```bash
cp .env.example .env
chmod 600 .env
```

2. 准备真实任务需要的上下文 tokenizer 和本地判断资源：

```bash
make context-setup
make judgment-setup
```

前者下载固定 tokenizer，后者安装可选判断依赖并下载固定 Laya 权重。两者均需要联网，缺少资源时不会自动伪造结果。这是推理/上下文准备，不是训练步骤；训练由最终部署环境单独配置。

3. 首次使用可直接 `make dev`。默认 demo.toml 同时提供真实任务入口和单独演示入口，并允许向 DeepSeek 发送已声明 public 的数据。

如果希望关闭演示入口，在 `.auton_local/dev.toml` 保存下方配置，再显式选择它。仅使用仓库的 dev.toml 不会自动授权远程 provider：

```toml
profile = "dev"
implementation = "disabled"

[constitution]
remote_providers = ["deepseek"]

[models]
backend = "deepseek"
secret_reference = "DEEPSEEK_API_KEY"
```

```bash
AUTON_CONFIG=.auton_local/dev.toml make dev
```

先创建 `.auton_local` 目录再保存文件。密钥从 `.env` 或进程环境读取，不写入 TOML。真实模型请求使用 API 额度；只启动服务不自动执行付费验收脚本。

4. 在模型页查看资源/连接状态，然后在资产页建立项目并审核资料，在工具页建立工作区，再到任务页选择项目、工作区、模型、目标和验收。远程执行前明确确认输入可公开，文件写入逐项批准。完整步骤见 [功能指南](usage.md)。

本地判断目前为建议模式；没有通过质量门槛就不会自动采用。浏览器和 CLI 默认是不同身份。

## 分开启动与自定义端口

```bash
make api
# 另一个终端
make web
```

Make 启动参数对应 Python 工具 `scripts/dev.py all|api|web`。它的 all/api 固定使用 8000/5173 默认端口，不要用环境变量误以为已经改变后端监听端口。

需要自定义端口时，直接运行 uvicorn，并为前端代理设置同一个 API 端口：

```bash
AUTON_CONFIG=.auton_local/dev.toml .venv/bin/python -m uvicorn auton.bootstrap.app:create_app --factory --host 127.0.0.1 --port 8001
# 另一个终端
AUTON_API_PORT=8001 AUTON_WEB_PORT=5174 make web
```

同时在自定义 TOML 的根字段 `allowed_origins` 中加入实际使用的 `http://127.0.0.1:5174`、`http://127.0.0.1:8001`；根字段应写在 `[constitution]` 等模块表之前。当前服务面向回环地址，不通过改监听地址直接提供公网账号服务。

## 常见问题

| 现象 | 处理 |
| --- | --- |
| uv、npm、Git 不存在 | 先安装上述运行工具；不要用 make setup 代替运行工具安装 |
| 端口被占用 | 停止自己不再使用的服务，或按上文换端口；启动器不会杀其他进程 |
| 模型缺凭据或外发被拒绝 | 核对 `.env`/环境变量、配置的 secret_reference、remote_providers 和任务 public 声明 |
| tokenizer/判断权重缺失 | 执行对应 setup，或配置资源目录；启动不会自动下载 |
| 写入停在等待审批 | 在任务/工具页检查 diff，确认后逐项批准；不是执行卡死 |
| 训练/后台显示禁用 | 属于默认行为；按部署说明配置训练镜像、数据或明确计划，不改成测试替身 |
| 重启后找不到旧项目 | 使用原浏览器/CLI 身份；不要删除私有身份数据。旧身份迁移见功能指南 |
| 数据或任务结果未知 | 先在轨迹/工具凭据中对账，再显式恢复，避免重放副作用 |

完整配置参数见 [配置指南](configuration.md)；部署训练、灰度与长期运行见 [运行时发布](local-runtime-and-release.md) 和 [后台运行](background-operations.md)。
