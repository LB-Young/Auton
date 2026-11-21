# MCP stdio：进程边界与消息理解笔记

- 原链接：[MCP 2025-11-25 Transports](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports)
- 查阅：2026-11-17；本文为理解笔记。

stdio 通过子进程的 stdin/stdout 交换逐行 UTF-8 JSON-RPC。stdout 不能混入普通日志；stderr 单独处理。连接中断和工具业务失败也要区分，不能把没有收到结果解释成工具肯定没运行。

Auton 首个适配器固定启动本地 SHA256 服务，完成初始化、发现、调用与返回校验。它是一个可运行的窄协议适配，不等于已经支持所有 MCP 服务；暂不处理服务端发起请求、分页和远程 HTTP，也不继承云端密钥。后续接外部服务必须重新明确允许工具和副作用边界。
