# LLM — LLM 接口层

多 Provider 统一抽象，Router 按任务类型/模型特性选择 Provider。

## 目录结构

| 文件 | 职责 |
|------|------|
| `base.py` | ★ LLM Provider 抽象基类：`stream(messages, tools)` → AsyncIterator[Event] |
| `anthropic_provider.py` | Anthropic Claude 实现：支持 streaming、tools、reasoning |
| `openai_provider.py` | OpenAI GPT 实现：支持 streaming、tools |
| `ollama_provider.py` | Ollama 本地模型实现 |
| `router.py` | LLM 路由器：按任务类型（coding/reasoning/creative）选择模型和 Provider |
| `prompt.py` | Prompt 模板管理：SystemPrompt / ToolDescription / MemoryInjection 的模板 |

## 设计要点

- **Provider 接口**：所有 Provider 实现统一的 `stream()` 接口，返回异步事件流
- **Router 策略**：按任务类型、上下文长度、预算选择 Provider；支持手动 `/model` 覆盖
- **事件化输出**：Provider 输出不是裸字符串，而是 TextDelta / ReasoningDelta / ToolCall 等结构化事件
- **Prompt 组成**：SystemPrompt = base_prompt + auton.md + memory_chunks + skill_injections
