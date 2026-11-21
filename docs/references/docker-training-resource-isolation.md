# Docker：训练资源与隔离

- 原链接：[Docker：训练资源与隔离](https://docs.docker.com/engine/containers/resource_constraints/)
- 核对日期：2026-11-19。以下是自己的理解笔记，不是原文副本。

容器默认没有资源限制，需要部署方明确设置内存、CPU、进程数和超时。Auton 参考执行器关闭网络、禁止自动 pull、丢弃 capabilities，以普通用户运行；基础模型与输入只读，只挂载本次输出目录，不挂载 provider 密钥、生产工具目录或 Docker socket。镜像由部署方审核并固定 digest。输出字节数由控制器巡检，worker 有单文件限制；这不等于 bind mount 有硬磁盘配额。Docker daemon、GPU 驱动与宿主机权限仍由部署运维管理。
