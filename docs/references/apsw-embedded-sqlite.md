# APSW：Python 内嵌 SQLite 驱动

- 原文：[Installation and customization](https://rogerbinns.github.io/apsw/install.html)
- 来源：APSW 官方；查阅：2026-11-17。中文理解笔记，非原文转载。

官方说明 PyPI 分发包含私有 SQLite 引擎，通常有预编译 wheel；不会替换 Python 标准库或系统其他应用所使用的 SQLite。不支持 wheel 的平台可能需要本地编译。

对 Auton 的理解：通过锁文件固定驱动/引擎，比假设所有用户的 Python 3.12 都带相同 SQLite 更可靠。M02 工厂隔离驱动，业务只访问 EventLogPort；磁盘操作放工作线程并明确序列化与事务语义。

驱动版本不替代应用层验收；必须实际检查引擎版本、WAL/FULL、迁移及故障行为。接口与标准库 sqlite3 不完全相同，不能直接照搬提交/异常处理代码。
