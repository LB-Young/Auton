---
name: ai-research
description: "获取知名AI团队（Anthropic、OpenAI、Google DeepMind）的最新研究动态和技术博客更新。适用于：追踪AI行业最新进展、了解前沿AI技术动态、获取AI研究趋势分析。"
user-invocable: true
metadata:
  openclaw:
    emoji: "🤖"
---

# AI Research Tracker

获取并整理知名AI团队的最新研究动态。

## 数据来源

| 团队 | 官方博客 | 侧重点 |
|------|----------|--------|
| **Anthropic** | https://www.anthropic.com/engineering | Claude平台、Agent开发、安全对齐 |
| **OpenAI** | https://openai.com/research 或 https://openai.com/zh-Hans-CN/research/ | GPT系列、安全研究、科学应用 |
| **Google DeepMind** | https://deepmind.google/research/ | Gemini、AlphaFold、机器人与科学 |

## 执行流程

### 步骤1：访问页面

使用浏览器依次访问以下三个页面：

```
1. https://www.anthropic.com/engineering
2. https://openai.com/zh-Hans-CN/research/
3. https://deepmind.google/research/
```

### 步骤2：提取内容

使用 `browser` 工具的 `evaluate` action 执行以下JavaScript提取页面内容：

```javascript
JSON.stringify({
  title: document.title,
  headings: Array.from(document.querySelectorAll('h1, h2, h3')).map(h => ({
    tag: h.tagName, 
    text: h.textContent.trim()
  })).slice(0, 30),
  mainText: document.body.innerText.slice(0, 5000)
})
```

### 步骤3：整理报告

根据提取的内容，按以下格式整理报告：

```markdown
# 🤖 知名AI团队最新研究摘要

> 获取时间：[当前日期]

## 🏢 Anthropic 最新动态

[从页面提取最新文章列表，包括标题、日期、简介]

## 🚀 OpenAI 最新动态

[从页面提取最新研究列表]

## 🧠 Google DeepMind 最新动态

[从页面提取最新突破和新闻]

## 📊 综合分析

[分析三家公司的共同关注领域和趋势差异]
```

## 内容提取要点

### Anthropic Engineering 页面
- 查找 `h2` 和 `h3` 标题中的文章列表
- 关注时间标记（如 "Mar 25, 2026"）
- 提取 Featured 标记的重点文章

### OpenAI Research 页面
- 查找分类标签（研究/安全/产品/刊发）
- 提取文章标题和摘要
- 注意时间排序

### Google DeepMind Research 页面
- 关注 Breakthroughs（突破）部分
- 提取 Latest news（最新新闻）
- 查看 Publications（学术论文）

## 输出格式要求

1. **结构化表格**：使用表格展示文章列表，包含时间、标题、简介
2. **分类清晰**：按公司分组，每个公司独立一个板块
3. **趋势分析**：最后添加综合分析，对比三家的研究方向
4. **快速链接**：在结尾提供官方链接

## 注意事项

- ⚠️ 如果某些页面加载失败，可以单独重试
- 💡 DeepMind页面可能有动态加载内容，可适当等待后截图
- 🔄 建议按顺序访问：Anthropic → OpenAI → DeepMind

## 示例输出结构

```
# 🤖 知名AI团队最新研究摘要
> 获取时间：2026年3月

## 🏢 Anthropic
| 时间 | 标题 | 简介 |
|------|------|------|
| ... | ... | ... |

## 🚀 OpenAI
...

## 🧠 Google DeepMind
...

## 📊 综合分析
| 领域 | Anthropic | OpenAI | DeepMind |
|------|-----------|--------|----------|
| Agent | ✅ | ... | ... |
| 安全 | ... | ... | ... |
...
```
