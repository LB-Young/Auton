# Commands — 斜杠命令系统

命令是第一公民的统一交互接口，与自然语言并列。Command Registry 聚合所有命令。

## 目录结构

| 文件 | 职责 | 状态 |
|------|------|------|
| `base.py` | ★ 命令基类：`name / description / patterns / handle()` | ✅ |
| `context.py` | ★ 命令上下文：CommandContext（session/config/io） | ✅ |
| `registry.py` | ★ 命令注册表：`get_command_registry()` 单例 | ✅ |
| `help.py` | `/help` — 显示所有可用命令 | ✅ |
| `model.py` | `/model` — 查看/切换 LLM 模型 | ✅ |
| `config_cmd.py` | `/config get/set` — 读写配置项 | ✅ |
| `compact.py` | `/compact` — 手动触发上下文压缩 | ✅ |
| `plan.py` | `/plan` — 进入计划模式 | ✅ |
| `session_cmd.py` | `/session` — 当前会话信息 | ✅ |
| `memory_cmd.py` | `/memory` — 记忆管理 | 🟡 stub |
| `skill_cmd.py` | `/skill` — 技能管理 | 🟡 stub |
| `cron_cmd.py` | `/cron` — 定时任务管理 | 🟡 stub |
| `tasks_cmd.py` | `/tasks` — 后台任务管理 | 🟡 stub |

✅ = 已完成    🟡 = stub（对应子系统未就绪）

## 命令架构

```
用户输入 "/help"
    → SessionProcessor._try_handle_command()
    → CommandRegistry.match("/help")
    → HelpCommand.handle(args)
    → CommandResult(content="...")
    → CLI 渲染 Markdown 输出
```

## 内置命令

### ✅ /help
显示所有已注册命令及其描述。

### ✅ /model
查看可用模型或切换模型（stub，切换需要重启 CLI）。

### ✅ /config
```
/config              — 显示配置说明
/config get <key>    — 读取配置值
/config set <key> <value>  — 写入配置（运行时）
```

### ✅ /compact
手动触发上下文压缩，保留首尾消息，中间历史压缩为摘要。

### ✅ /plan
```
/plan                      — 显示计划模式说明
/plan <task>               — 触发计划（完整功能在 M8 实现）
```

### ✅ /session
```
/session              — 当前会话信息
/session current      — 同上
/session list         — 历史会话列表（stub）
```

### 🟡 /memory (M4)
```
/memory list          — 列出记忆
/memory get <id>      — 查看单条记忆
/memory edit <id>     — 编辑记忆
/memory delete <id>   — 删除记忆
/memory gc            — 触发遗忘机制
```

### 🟡 /skill (M6)
```
/skill list           — 列出所有技能
/skill info <name>    — 查看技能详情
/skill create         — 创建新技能（触发 skill-creator）
/skill delete <name>  — 删除技能
/skill edit <name>   — 编辑技能
/skill check         — 检查技能依赖
/skill install <file> — 从 .skill 包安装
```

### 🟡 /cron (M8)
```
/cron list            — 列出所有定时任务
/cron add <name> <schedule> — 添加任务
/cron edit <name>    — 编辑任务
/cron remove <name>  — 删除任务
/cron run <name>     — 立即执行
/cron enable <name>   — 启用任务
/cron disable <name> — 禁用任务
/cron logs <name>    — 查看执行日志
```

### 🟡 /tasks (M9)
```
/tasks list           — 列出所有任务及状态
/tasks get <id>      — 获取任务输出
/tasks stop <id>     — 停止任务
```

## 新增命令

在 `auton/commands/` 目录下新建 `.py` 文件即可：

```python
from .base import Command, CommandResult

class MyCommand(Command):
    name = "mycommand"
    description = "我的自定义命令"
    patterns = [
        ("/mycommand",),
        ("/mycommand", "<arg>"),
    ]

    async def handle(self, args: dict) -> CommandResult:
        return CommandResult(content=f"Hello {args.get('<arg>', 'world')}")

# 在 registry.py 中注册
registry.register(MyCommand())
```
