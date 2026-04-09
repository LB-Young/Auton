# Workflow — 工作流引擎

将重复性工作封装为可复用工作流 DSL，支持断点续执。

## 目录结构

| 文件 | 职责 |
|------|------|
| `engine.py` | 工作流执行引擎：解析 DSL，执行节点图，驱动状态机 |
| `parser.py` | 工作流 DSL 解析器：文本 DSL → 结构化节点图（YAML/JSON） |
| `nodes.py` | 工作流节点类型：task / branch / loop / parallel / wait |
| `context.py` | 工作流执行上下文：变量绑定、节点输出传递 |
| `checkpoint.py` | 断点管理：每节点执行后保存 checkpoint，支持从断点恢复 |

## DSL 示例
```yaml
workflow: deploy-service
steps:
  - id: build
    type: task
    command: docker build -t myapp .
  - id: test
    type: task
    command: docker run myapp pytest
    depends_on: [build]
  - id: deploy
    type: branch
    condition: "{{ env.DEPLOY_ENV == 'prod' }}"
    on_true:
      - type: task
        command: kubectl apply -f k8s/prod.yaml
    on_false:
      - type: task
        command: kubectl apply -f k8s/staging.yaml
    depends_on: [test]
```

## 设计要点

- **节点类型**：task（原子任务）/ branch（条件分支）/ loop（循环）/ parallel（并行）/ wait（等待）
- **依赖表达**：`depends_on` 声明有向无环图（DAG），支持拓扑排序并行执行
- **断点续执**：每节点执行后保存 checkpoint JSON，重启后从最后一个成功节点恢复
- **上下文变量**：`{{ variable }}` 模板语法，节点间传递输出
