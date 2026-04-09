# Security — 安全与权限

## 目录结构

| 文件 | 职责 |
|------|------|
| `permission.py` | ★ 四模式权限检查器：default（交互确认）/ auto（ML 自动审批低风险）/ bypass（跳过所有）/ yolo（全部拒绝） |
| `audit.py` | 操作审计日志：所有工具调用写入 `data/logs/audit/`，含时间、操作者、参数、结果 |
| `path_validator.py` | 路径安全校验：遍历攻击防御 / Unicode 标准化 / 符号链接穿透 |
| `command_classifier.py` | 命令读写语义分类：识别 read-only / write / destructive / network 操作 |
| `key_manager.py` | 密钥管理：不存明文，从 env / macOS Keychain / gopass 读取 |

## 四模式权限

| 模式 | 行为 | 适用场景 |
|------|------|---------|
| `default` | 交互式确认（每次写操作询问） | 默认模式 |
| `auto` | ML 分类器自动审批低风险操作 | `--auto` 标志 |
| `bypass` | 跳过所有权限检查 | 明确 opt-in，危险 |
| `yolo` | 全部自动拒绝（只读） | 安全研究 / CI |

## 设计要点

- **BashTool 最危险**：7 层校验（command_classifier → path_validator → 危险命令过滤 → 超时限制 → 沙箱隔离 → 输出截断 → audit）全部在 `permission.py` 协调下执行
- **Prompt Injection 防护**：工具结果中特殊字符（`#`、`/`、`---`）在传入 LLM 前转义
- **审计不可绕过**：所有工具调用必须经过 `audit.py` 记录，无论权限模式为何
- **密钥零存储**：凭据不写入任何文件，始终从 env 或 OS 密钥链读取
