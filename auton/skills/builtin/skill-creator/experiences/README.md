# skill-creator 使用经验

本文档记录本 skill 在实际使用中积累的经验和教训，每次使用后可选择追加新条目。
LLM 在执行本 skill 时读取此文件，避免重复犯错、复用成功路径。

## 经验条目

### 2026-04-07: SKILL.md body 保持精简
- **场景**：将大量 API 文档直接写入 SKILL.md body，导致 context 膨胀。
- **教训**：详细参考文档应放在 `references/` 目录，只在 SKILL.md 主体中保留核心工作流和关键示例。
- **标签**：#context #documentation
