# Tools — 工具系统

每个工具独立目录，逻辑、Schema、工具描述放一起。Registry 统一管理所有工具。

## 目录结构

| 子目录 | 职责 | 状态 |
|--------|------|------|
| `registry.py` | ★ 工具注册表：合并内置 + MCP + 插件，统一 schema 和 handler | ✅ |
| `base.py` | ★ 工具基类：输入 Schema 验证 + 执行接口 | ✅ |
| `read/` | 文件读取 | ✅ |
| `write/` | 文件写入 | ✅ |
| `edit/` | 字符串替换编辑（幂等） | ✅ |
| `bash/` | Shell 执行：7 层安全校验 + 沙箱隔离 | ✅ |
| `bash/security.py` | 危险命令过滤 / 读写语义分类 | ✅ |
| `bash/path_validator.py` | 路径遍历 / Unicode 标准化 / 符号链接检测 | ✅ |
| `bash/sandbox.py` | macOS sandbox-exec / Linux bwrap 隔离 | ✅ |
| `glob/` | 文件路径模式匹配 | ✅ |
| `grep/` | 正则内容搜索 | ✅ |
| `web_search/` | Web 搜索（stub） | ✅ |
| `web_fetch/` | URL 内容抓取 | ✅ |
| `git/` | Git 操作（透传 bash） | ✅ |
| `http/` | HTTP API 请求 | ✅ |
| `task_create/` | 创建后台任务（stub） | 🟡 |
| `task_get/` | 查询任务状态（stub） | 🟡 |
| `task_list/` | 列出所有任务（stub） | 🟡 |
| `mcp/` | MCP 协议适配器：JSON-RPC stdio 通信 | ✅ |

✅ = 已完成    🟡 = 部分实现（stub）

## 工具注册表（registry.py）

```python
from auton.tools import get_registry

registry = get_registry()
tools = registry.get_tools()        # 获取所有已注册工具
schemas = registry.schemas()         # 获取所有工具 schema（供 LLM）
tool = registry.get("bash")          # 按名称查找
registry.enable("bash")             # 启用工具
registry.disable("bash")            # 禁用工具
summary = registry.summary()        # 注册表摘要
```

**内置工具**（`src/auton/tools/`）：
```
read / write / edit / glob / grep / bash / web_search / web_fetch
```

**MCP 工具**（动态注册）：
```python
# ~/.auton/config/auton_config.json
{
  "global": {
    "mcp": {
      "servers": [
        {
          "name": "github",
          "command": ["npx", "-y", "@modelcontextprotocol/server-github"],
          "env": {
            "GITHUB_TOKEN": "${GITHUB_TOKEN}"
          }
        }
      ]
    }
  }
}
```

## BashTool 7 层安全防线

| 层级 | 模块 | 检查内容 |
|------|------|----------|
| 1 | `security.py` → `classify_command()` | 读写语义分类（read-only/write/destructive） |
| 2 | `path_validator.py` → `validate_command_paths()` | 路径遍历、Unicode 标准化、符号链接穿透 |
| 3 | `security.py` → `DANGEROUS_PATTERNS` | `rm -rf /`、`curl\|sh` 等黑名单 |
| 4 | `BashTool.execute()` 超时参数 | 命令执行超时自动 kill |
| 5 | `sandbox.py` → `run_sandboxed()` | macOS sandbox-exec / Linux bwrap |
| 6 | `BashTool.execute()` → `truncate_output()` | STDOUT/STDERR 截断到 1MB |
| 7 | `BashTool.execute()` → `write_audit_log()` | 所有调用写入审计日志（~/.auton/logs/commands.log） |

### 危险命令示例

```python
# ✅ 允许：ls / cat / grep — read_only
# ⚠️  需要确认：sudo / chmod / curl — write
# ❌  立即拒绝：rm -rf / / curl|sh / mkfs — destructive
```

## 设计要点

- **工具自包含**：每个工具目录内含 `__init__.py`（Tool 子类）
- **注册表统一管理**：SessionProcessor 通过注册表获取工具，无感知来源差异
- **幂等性**：edit 工具的 old 字符串必须精确匹配
- **审计不可绕过**：所有 bash 调用写入 commands.log，即使 sandbox 关闭也生效
