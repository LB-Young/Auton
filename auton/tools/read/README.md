# Read Tool

文件读取工具，支持路径通配符和内容限制。

## 输入 Schema
- `path: str` — 文件路径，支持 `*` 和 `**/*.py` 通配符
- `limit: int | None` — 最大行数（可选）
- `offset: int | None` — 起始行号（可选，从 1 开始）

## 输出
文件内容字符串，超限自动截断并注明 `[...N lines truncated]`

## 设计要点
- 路径经过 `security/path_validator.py` 校验后执行
- 通配符展开调用 `glob.glob()`，返回文件列表
- 大文件（>1MB）默认只读前 1000 行，需显式指定 `limit`
