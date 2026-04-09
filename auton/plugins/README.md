# Plugins — 插件系统

通过插件扩展 Agent 底层能力，支持热加载和沙箱隔离。

## 目录结构

| 文件 | 职责 |
|------|------|
| `loader.py` | 插件加载器：importlib + 热加载，支持从 `plugins/` 目录扫描 |
| `base.py` | 插件基类：定义 `on_load()` / `on_unload()` / `on_tool_call()` 生命周期钩子 |
| `registry.py` | 插件注册表：管理插件启用/禁用/优先级 |
| `sandbox.py` | 插件沙箱隔离：插件代码在受限 namespace 执行，禁止访问系统命令 |

## 设计要点

- **生命周期钩子**：`on_load`（加载时）/ `on_tool_call`（工具调用前后）/ `on_message`（消息处理）/ `on_unload`（卸载时）
- **热加载**：插件更新后无需重启 Auton，通过 importlib.reload 重新加载
- **沙箱隔离**：插件执行在 ` RestrictedPython` 或 `multiprocessing` 受限环境中，禁止 os.system / subprocess
- **权限降级**：插件默认权限低于内置工具，禁止执行 `rm -rf` 等高危操作
