# Edit Tool

字符串替换编辑工具，幂等、安全、可回退。

## 输入 Schema
- `path: str` — 文件路径
- `old_string: str` — 必须精确匹配的原始字符串
- `new_string: str` — 替换后的新字符串
- `create_file: bool = false` — `old_string` 不存在时是否创建文件

## 输出
`ok` 或 `old_string not found in file`

## 设计要点
- **幂等性**：`old_string` 必须精确匹配，不存在时返回错误，不做任何修改
- **上下文完整性**：替换前后的内容不截断，保持文件完整性
- **回退支持**：edit 执行前将当前内容追加到 `snapshot.py` 的 patch 日志
- 路径经过 `security/path_validator.py` 校验
