# Write Tool

文件写入工具，原子写入防止数据丢失。

## 输入 Schema
- `path: str` — 文件路径
- `content: str` — 文件内容
- `create_dirs: bool = false` — 是否自动创建父目录

## 输出
`ok` 或错误信息

## 设计要点
- **原子写入**：先写临时文件（`.tmp.{uuid}`），内容写完后 `os.rename()` 替换原文件
- `os.rename` 是原子操作（POSIX），可防止半写状态导致文件损坏
- 父目录不存在时默认报错（`create_dirs=false`），防止误创目录
- 路径经过 `security/path_validator.py` 校验
