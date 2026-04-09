# Bash Tool

Shell 执行工具，最危险工具，需要 7 层安全校验。

## 输入 Schema
- `command: str` — Shell 命令
- `timeout: int = 60` — 超时秒数（默认 60s）
- `working_dir: str | None` — 工作目录（可选）

## 7 层安全校验（bash/security.py）

| 层级 | 模块 | 检查内容 |
|------|------|----------|
| 1 | command_classifier | 读写语义分类（read-only / write / destructive） |
| 2 | path_validator | 路径遍历攻击、Unicode 标准化、符号链接穿透 |
| 3 | 危险命令过滤 | `rm -rf /` / `mkfs` / `:(){:\|:&};:` 等 |
| 4 | 超时限制 | 命令执行超时自动 kill |
| 5 | sandbox | Linux namespaces / macOS sandbox 隔离 |
| 6 | 输出截断 | STDOUT/STDERR 截断到 1MB |
| 7 | audit | 所有调用写入审计日志（不可绕过） |

## 沙箱策略（bash/sandbox.py）

- **Linux**：unshare + chroot 到只读根文件系统，仅允许 `/tmp/auton-workspace`
- **macOS**：`sandbox-exec` 配置文件，限制文件系统/网络访问

## 设计要点

- **逐层防御**：任何一层拒绝，整个命令被拒绝
- **可配置**：本地模式 7 层全开，CI 环境可关闭沙箱层
- **输出截断**：防止 `cat /dev/urandom` 等命令导致内存溢出
