# Skills — 技能系统

Skill 是一个带 YAML frontmatter 的 Markdown 文件（SKILL.md），**本质是知识文档，不是可执行代码**。
当用户请求涉及某个领域时，Auton 把对应 Skill 的内容注入 LLM 上下文，
让 LLM 知道在这个场景下应该用什么工具、按什么步骤操作。

## 目录结构

| 文件 | 职责 | 状态 |
|------|------|------|
| `types.py` | Skill / SkillSource 类型定义 | ✅ |
| `frontmatter.py` | YAML frontmatter 解析 + schema 验证 | ✅ |
| `loader.py` | SkillLoader：从各路径扫描 SKILL.md 并解析 | ✅ |
| `registry.py` | SkillRegistry：全局单例注册表 | ✅ |
| `semantic_search.py` | SkillSearcher：关键词语义检索 | ✅ |
| `injector.py` | SkillInjector：构建 system prompt 片段 | ✅ |
| `checker.py` | SkillChecker：依赖检查（bins/权限） | ✅ |
| `packager.py` | SkillPackager：打包/解压 .skill（zip） | ✅ |
| `skill_creator.py` | SkillCreator：skill-creator 元技能逻辑 | ✅ |
| `builtin/` | 内置技能目录 | ✅ |
| `builtin/skill-creator/` | 🛠️ 元技能：创建新技能 | ✅ |
| `builtin/github/` | 🐙 GitHub 操作（gh CLI） | ✅ |
| `builtin/git-workflow/` | 🌿 标准化 Git 工作流 | ✅ |
| `builtin/web-search/` | 🔍 网页搜索与内容抓取 | ✅ |
| `builtin/code-review/` | 🔍 代码审查（质量/安全/模式） | ✅ |

✅ = 已完成

## Skill 目录结构

```
<skill-name>/
├── SKILL.md              # ★ 必需（YAML frontmatter + Markdown 知识）
├── scripts/              # 可选：可执行脚本，直接运行不占 context
├── references/           # 可选：参考文档，按需加载
├── assets/               # 可选：输出资产，不加载入 context
└── experiences/          # 可选：使用经验记录
    └── README.md         # 经验条目（日期/场景/教训/标签）
```

## SKILL.md frontmatter 关键字段

```yaml
---
name: github
description: "何时使用 / 何时不用，LLM 据此判断是否注入"
disable-model-invocation: false  # 是否禁止 LLM 自动调用
user-invocable: true           # 是否允许手动触发
load-experiences: true          # 是否自动加载 experiences/README.md
metadata:
  openclaw:
    emoji: "🐙"
    requires:
      bins: ["gh"]              # 依赖的二进制命令
    install:
      - kind: brew
        formula: gh
---
```

## 渐进式披露

| 层级 | 内容 | 何时加载 |
|------|------|----------|
| 元数据 | name + description | 始终在 context |
| SKILL.md body | 工作流、工具说明、示例 | Skill 触发后 |
| experiences/ | 使用经验、教训 | Skill 触发后（load-experiences=true） |
| references/ | 详细文档、表结构 | 按需（LLM 决定） |
| scripts/ | 可执行脚本 | 直接运行 |

## 技能来源优先级

1（最高）`.auton/skills/`（工作区）> 2 `.auton/skills/`（项目）> 3 `~/.auton/skills/`（用户）> 4 `src/auton/skills/builtin/`（内置）

同名技能高优先级覆盖低优先级。

## 快速使用

```python
from auton.skills import SkillRegistry, SkillInjector, SkillChecker

# 注册表
registry = SkillRegistry.get_instance()
registry.ensure_loaded()
print(f"共 {len(registry)} 个技能")
for s in registry:
    print(f"  {s.name} ({s.source.value})")

# 注入相关 skill
injector = SkillInjector(registry)
context = injector.inject_for_query("review a GitHub PR", top_k=3)

# 依赖检查
checker = SkillChecker(registry)
report = checker.check_all_and_report()
```

```bash
# CLI
auton --msg "/skill list"
auton --msg "/skill info github"
auton --msg "/skill search github"
auton --msg "/skill check"
```
