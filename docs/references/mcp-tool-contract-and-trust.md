# MCP Tools：schema 与信任边界笔记

- 原链接：[MCP 2025-11-25 Tools](https://modelcontextprotocol.io/specification/2025-11-25/server/tools)
- 查阅：2026-11-17；本文为理解笔记。

发现返回工具名和输入 schema；调用返回内容，并可提供结构化结果。JSON-RPC 错误、工具的 isError 和业务成功分别判断，不能因 HTTP/进程仍在就宣称调用成功。

工具注解只能提供提示。Auton 的首次接入使用固定服务、工具名和输入 schema 白名单，权限来自自身策略；不让 readOnlyHint 授权任意工具。SHA256 结果还按本地预期值核对。即使结构正确，工具文本依然是数据，不能成为系统指令或权限变更。
