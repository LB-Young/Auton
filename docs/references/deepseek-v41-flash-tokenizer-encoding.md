# DeepSeek V4.1 Flash：tokenizer 与会话编码笔记

整理日期：2026-11-18。本文为理解笔记，原始资料见链接。

原链接：[官方编码说明](https://huggingface.co/deepseek-ai/DeepSeek-V4.1-Flash/blob/314113f8a7dadb388215396ba5fbee2c610a04d6/encoding/README.md)、[官方编码实现](https://huggingface.co/deepseek-ai/DeepSeek-V4.1-Flash/blob/314113f8a7dadb388215396ba5fbee2c610a04d6/encoding/encoding.py)、[tokenizer](https://huggingface.co/deepseek-ai/DeepSeek-V4.1-Flash/blob/314113f8a7dadb388215396ba5fbee2c610a04d6/tokenizer.json)。

## 我的理解

输入 token 不是各段自然语言长度之和。角色、轮次边界、工具定义、工具调用参数与工具响应都影响最终编码。预算必须用将要发送的消息结构套入对应模型编码，再经过 tokenizer；直接按字数计算只能作为保守保护，不能冒充真实 token 数。

Flash V4.1 与 Pro V4 的模板不同，不能因模型同属于 DeepSeek 就共用编码文件。工具 schema 应按编码器要求附在首条 system 消息上。编码已包含起始特殊 token，调用底层 tokenizer 时不能重复添加。

## Auton 中的应用

M08 固定上述 commit，对 tokenizer JSON 校验 Git blob SHA1 与文件大小；保留原始编码代码及许可证。缺文件、摘要不符、消息模板不兼容都明确阻塞，不换近似 tokenizer 或测试替身。

运行路径只支持文本和关闭 thinking 的 chat 模式，与当前 M04 provider 一致。测试中另行检查中文、英文与完整工具轮次；未来支持思考模式或多模态时必须扩展版本与契约。

公开 tokenizer 不能证明云端隐藏前缀与别名永远不变，因此同时保留保守准入预算，计费和结算采用云端响应 usage。M08 两次短文本样例中，装配后的 Flash 本地计数与远端均为 213；这个样例不代表所有工具、格式或未来版本都完全相等。
