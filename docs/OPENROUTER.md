# OpenRouter 配置指南

OpenRouter 是一个统一的 LLM API 网关，支持多个模型提供商。本项目通过 LiteLLM 支持 OpenRouter。

## 快速配置

### 1. 获取 API Key

访问 [OpenRouter](https://openrouter.ai/) 注册并获取 API Key（格式：`sk-or-v1-...`）

### 2. 配置环境变量

在 `.env` 文件中添加：

```bash
# OpenRouter 配置
LLM_API_KEY="sk-or-v1-your-key-here"
LLM_API_BASE="https://openrouter.ai/api/v1"
LLM_MODEL="openrouter/anthropic/claude-3.5-sonnet"
```

## 可用模型

OpenRouter 支持多个提供商的模型，格式为 `openrouter/provider/model`：

### Anthropic Claude
```bash
LLM_MODEL="openrouter/anthropic/claude-3.5-sonnet"
LLM_MODEL="openrouter/anthropic/claude-3-opus"
```

### OpenAI
```bash
LLM_MODEL="openrouter/openai/gpt-4o"
LLM_MODEL="openrouter/openai/gpt-4-turbo"
LLM_MODEL="openrouter/openai/o1-preview"
```

### Google
```bash
LLM_MODEL="openrouter/google/gemini-pro-1.5"
LLM_MODEL="openrouter/google/gemini-flash-1.5"
```

### Meta
```bash
LLM_MODEL="openrouter/meta-llama/llama-3.1-70b-instruct"
LLM_MODEL="openrouter/meta-llama/llama-3.1-405b-instruct"
```

### Mistral
```bash
LLM_MODEL="openrouter/mistralai/mistral-large"
LLM_MODEL="openrouter/mistralai/mistral-medium"
```

## 完整示例

```bash
# .env 文件
LLM_API_KEY="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"
LLM_API_BASE="https://openrouter.ai/api/v1"
LLM_MODEL="openrouter/anthropic/claude-3.5-sonnet"

AGENT_MAX_STEPS=50
AGENT_WORKSPACE_DIR="./workspace"
ENABLE_MCP=true
ENABLE_SKILLS=true
```

## 测试配置

启动服务：
```bash
make dev
```

访问 API 文档：
```
http://localhost:8000/docs
```

测试调用：
```bash
curl -X POST "http://localhost:8000/api/v1/agent/run" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Hello, test the OpenRouter connection"
  }'
```

## 注意事项

1. **API Key 安全**：不要将 API Key 提交到版本控制系统
2. **费用控制**：OpenRouter 按实际使用计费，建议设置预算限制
3. **模型选择**：不同模型的定价和能力不同，参考 [OpenRouter Pricing](https://openrouter.ai/docs#models)
4. **Tool Calling**：确保选择的模型支持 function calling 功能

## 常见问题

### Q: 如何查看可用模型？
A: 访问 [OpenRouter Models](https://openrouter.ai/docs#models)

### Q: 为什么某些模型不支持 tool calling？
A: 不是所有模型都支持 function calling，建议使用：
- Claude 3.5 Sonnet
- GPT-4o
- Gemini 1.5 Pro

### Q: 如何切换到直连 API？
A: 只需修改环境变量：
```bash
# 从 OpenRouter 切换到 Anthropic 直连
LLM_API_KEY="sk-ant-your-key"
LLM_API_BASE="https://api.anthropic.com"
LLM_MODEL="anthropic/claude-3-5-sonnet-20241022"
```

## 更多信息

- [OpenRouter 文档](https://openrouter.ai/docs)
- [LiteLLM OpenRouter 支持](https://docs.litellm.ai/docs/providers/openrouter)
- [项目 README](./README.md)
