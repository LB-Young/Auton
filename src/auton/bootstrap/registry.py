from auton.kernel.modules import ModuleDescriptor

PLANNED = (
    ("model", "执行模型网关", "M04"),
    ("judgment", "Jev 判断与路由", "M05"),
    ("tools", "工具宿主", "M06"),
    ("genome", "资产与记忆", "M07"),
    ("context", "上下文引擎", "M08"),
    ("agent", "单 Agent 运行时", "M09"),
    ("experience", "轨迹与恢复", "M10"),
    ("server", "完整服务协议", "M11"),
    ("web", "完整工作台", "M12"),
    ("assess", "独立评估", "M13"),
    ("delegation", "多 Agent 委派", "M14"),
    ("evolve", "资产进化", "M15"),
    ("decision_review", "决策轨迹复核", "M16"),
    ("datasets", "训练数据快照", "M17"),
    ("executor_training", "执行模型训练", "M18"),
    ("decision_training", "决策模型训练", "M19"),
    ("release", "发布与回滚", "M20"),
    ("operations", "后台调度与监控", "M21"),
)


def module_catalog(demo: bool) -> list[ModuleDescriptor]:
    return [
        ModuleDescriptor(
            id="foundation",
            title="框架契约",
            milestone="M01",
            status="ready",
            provides=("core",),
            factory_entry="bootstrap.ApplicationFactory",
            config_schema="ApplicationConfig",
        ),
        ModuleDescriptor(
            id="kernel",
            title="持久事件内核",
            milestone="M02",
            status="ready",
            provides=("event_log",),
            requires=("core",),
            factory_entry="kernel.KernelFactory",
            config_schema="KernelConfig",
        ),
        ModuleDescriptor(
            id="constitution",
            title="固定策略与权限",
            milestone="M03",
            status="ready",
            provides=("policy",),
            requires=("event_log",),
            factory_entry="constitution.ConstitutionFactory",
            config_schema="ConstitutionConfig",
        ),
        ModuleDescriptor(
            id="demo",
            title="模拟会话",
            milestone="M01",
            status="ready" if demo else "disabled",
            provides=("conversation",),
            requires=("core",),
            factory_entry="demo.DemoConversationFactory",
            config_schema="DemoConfig",
        ),
        ModuleDescriptor(
            id="transport",
            title="API 与工作台骨架",
            milestone="M01",
            status="ready",
            provides=("http",),
            requires=("core", "event_log", "policy", "conversation")
            if demo
            else ("core", "event_log", "policy"),
            factory_entry="server.ServerFactory",
            config_schema="ServerConfig",
        ),
        *[
            ModuleDescriptor(id=key, title=title, milestone=milestone, status="planned")
            for key, title, milestone in PLANNED
        ],
    ]
