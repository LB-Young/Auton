# Task — 后台任务系统

独立于主会话的异步任务执行，支持状态机、输出文件、断点续执。

## 目录结构

| 文件 | 职责 |
|------|------|
| `types.py` | 任务类型：TaskType / TaskStatus / TaskHandle 定义 |
| `registry.py` | 任务注册表：持久化到磁盘，支持跨进程查询 |
| `executor.py` | 任务执行器：独立进程/线程池，执行 TaskHandle |
| `state_machine.py` | ★ 任务状态机：pending → running → completed / failed / killed（单向不可逆） |
| `output_file.py` | 任务输出文件：支持增量读取和断点续执（追加写入 + 文件指针） |

## 状态机
```
pending → running → completed
                   ↘ failed
                   ↘ killed
```
- `is_terminal(status)` 作为边界守卫，防止向已终止任务注入消息
- 状态不可逆单向转移

## 设计要点

- **独立执行**：任务在独立进程/线程中执行，不阻塞主 SessionProcessor
- **持久化注册表**：任务创建后持久化到 `data/tasks/registry.jsonl`，重启后可恢复
- **增量输出**：Task 输出写入 `data/tasks/outputs/{task_id}.log`，支持 `tail -f` 增量读取
- **断点续执**：任务失败后，通过 output_file.py 的文件指针恢复执行，不重复已完成部分
