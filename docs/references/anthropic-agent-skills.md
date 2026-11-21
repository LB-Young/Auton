# Anthropic：Equipping agents for the real world with Agent Skills

| 项 | 内容 |
|---|---|
| 机构 | Anthropic（Engineering） |
| 作者 | Barry Zhang、Keith Lazuka、Mahesh Murag |
| 发布 | 2025-10-16（2025-12-18 更新：Agent Skills 作为开放标准发布，见 agentskills.io） |
| 链接 | https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills |
| 主题 | Skill 的格式、渐进披露、捆绑脚本、开发与评估方法、安全 |

> 本文件为阅读笔记，非原文转载。

## 核心内容

- Skill 是由指令、脚本和资源组成的文件夹，Agent 可动态发现并加载；比喻为"新员工入职指南"，把过程性知识打包成可组合、可分享的单元。
- **格式**：最简形式是含 `SKILL.md` 的目录；YAML frontmatter 必需 `name` 和 `description`；可捆绑额外文件（如 `reference.md`、`forms.md`）和脚本。
- **渐进披露三层**：
  1. 启动时只把每个 skill 的 `name` 和 `description` 放进系统提示；
  2. 判断相关时读取完整 `SKILL.md`；
  3. 需要时再读取捆绑文件（如只在填表时读 `forms.md`）。
  因为 Agent 有文件系统和代码执行，可捆绑的内容"实际上不受限"。
- **捆绑脚本**：确定性操作用代码完成，比让模型逐 token 生成更便宜、更可靠；脚本可以直接执行，不必读进上下文。要写清楚某个脚本是"直接运行"还是"作为参考读取"。
- **开发方法**：
  - 从评估开始：在代表性任务上运行 Agent，找到能力缺口，再针对性地构建 skill；
  - 为规模组织：`SKILL.md` 臃肿时拆分文件；互斥内容分开放；
  - 从模型视角观察：看真实使用中的意外执行轨迹、对某些内容的过度依赖；特别注意 `name` 和 `description`，它们决定是否触发；
  - 与模型共同迭代：让模型把成功做法和常见错误沉淀进 skill；偏离轨道时让它反思原因。
- **安全**：恶意 skill 可能引入漏洞或诱导数据外泄；只从可信来源安装，审计捆绑文件、代码依赖和对外网络访问。
- **展望**：希望让 Agent 能自行创建、编辑和评估 skill，把自身行为模式固化为可复用能力（文中仅为展望）。

## 原文短句

- "Progressive disclosure is the core design principle that makes Agent Skills flexible and scalable."
- "Looking further ahead, we hope to enable agents to create, edit, and evaluate Skills on their own"

## 对 Auton 的启示

1. **skill 格式对齐开放标准**：`name` + `description` 必填，其余字段（checkpoints、domain 等）作为扩展；便于导入/导出社区 skill。
2. **`description` 是独立的可优化字段**：它决定触发。评测需要包含**触发准确率**（该用时是否用了、不该用时是否误用），由 `SkillRefiner` 单独优化 description。
3. **skill 可以捆绑脚本**：把 skill 中反复出现的确定性步骤固化为脚本（介于 skill 补丁与 `ToolSmith` 新建 tool 之间），风险等级同 tool（需人工审批 + 沙箱）。
4. **外部 skill 的安全审计**：导入的 skill 视为不可信资产，走 Guard 扫描与人工审批。
