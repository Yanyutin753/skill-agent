# Omni Agent - curl 请求示例

## 前置条件

确保服务已启动：
```bash
make dev
# 或
uv run uvicorn omni_agent.main:app --reload
```

## 基础示例

### 1. 健康检查

```bash
curl http://localhost:8000/health
```

**响应示例**:
```json
{
  "status": "healthy",
  "version": "0.1.0"
}
```

---

### 2. 查看可用工具

```bash
curl http://localhost:8000/api/v1/tools/
```

**响应示例**:
```json
{
  "tools": [
    {
      "name": "read_file",
      "description": "读取文件内容",
      "parameters": {...}
    },
    {
      "name": "write_file",
      "description": "写入文件内容",
      "parameters": {...}
    }
  ]
}
```

---

## Agent 任务示例

### 3. 简单任务 - Hello World

```bash
curl -X POST http://localhost:8000/api/v1/agent/run \
  -H "Content-Type: application/json" \
  -d '{
    "message": "你好！请介绍一下你自己"
  }'
```

**响应示例**:
```json
{
  "success": true,
  "message": "你好！我是由 Grok 驱动的 AI 助手...",
  "steps": 1,
  "logs": [...]
}
```

---

### 4. 文件操作 - 创建文件

```bash
curl -X POST http://localhost:8000/api/v1/agent/run \
  -H "Content-Type: application/json" \
  -d '{
    "message": "创建一个名为 hello.txt 的文件，写入 Hello from Grok!"
  }'
```

**响应示例**:
```json
{
  "success": true,
  "message": "文件 hello.txt 已成功创建，内容为：Hello from Grok!",
  "steps": 2,
  "logs": [
    {
      "type": "tool_call",
      "tool": "write_file",
      "arguments": {
        "file_path": "hello.txt",
        "content": "Hello from Grok!"
      }
    },
    {
      "type": "tool_result",
      "success": true,
      "execution_time": 0.001
    }
  ]
}
```

---

### 5. 文件操作 - 读取文件

```bash
curl -X POST http://localhost:8000/api/v1/agent/run \
  -H "Content-Type: application/json" \
  -d '{
    "message": "读取 hello.txt 文件的内容"
  }'
```

---

### 6. 复杂任务 - 多步骤

```bash
curl -X POST http://localhost:8000/api/v1/agent/run \
  -H "Content-Type: application/json" \
  -d '{
    "message": "创建文件 numbers.txt，写入数字 1 到 10（每行一个），然后读取并统计有多少个数字"
  }'
```

---

### 7. 代码执行（如果启用了 bash 工具）

```bash
curl -X POST http://localhost:8000/api/v1/agent/run \
  -H "Content-Type: application/json" \
  -d '{
    "message": "列出当前工作目录中的所有文件"
  }'
```

---

## 高级配置

### 8. 限制最大步数

```bash
curl -X POST http://localhost:8000/api/v1/agent/run \
  -H "Content-Type: application/json" \
  -d '{
    "message": "创建一个复杂的项目结构",
    "config": {
      "max_steps": 10
    }
  }'
```

---

### 9. 自定义工作目录

```bash
curl -X POST http://localhost:8000/api/v1/agent/run \
  -H "Content-Type: application/json" \
  -d '{
    "message": "创建文件 test.txt",
    "config": {
      "workspace_dir": "/tmp/my_workspace"
    }
  }'
```

---

### 10. 使用 Session（多轮对话）

**第一轮对话**:
```bash
curl -X POST http://localhost:8000/api/v1/agent/run \
  -H "Content-Type: application/json" \
  -d '{
    "message": "我的名字叫 Alice"
  }' | jq -r '.session_id'
```

**保存返回的 session_id，用于后续对话**:
```bash
SESSION_ID="<上一步返回的 session_id>"

curl -X POST http://localhost:8000/api/v1/agent/run \
  -H "Content-Type: application/json" \
  -d "{
    \"message\": \"你记得我的名字吗？\",
    \"session_id\": \"$SESSION_ID\"
  }"
```

---

## 使用 jq 过滤输出

### 11. 只显示结果消息

```bash
curl -s -X POST http://localhost:8000/api/v1/agent/run \
  -H "Content-Type: application/json" \
  -d '{
    "message": "1 + 1 等于多少？"
  }' | jq -r '.message'
```

---

### 12. 查看工具调用记录

```bash
curl -s -X POST http://localhost:8000/api/v1/agent/run \
  -H "Content-Type: application/json" \
  -d '{
    "message": "创建文件 test.txt"
  }' | jq '.logs[] | select(.type == "tool_call") | {tool, arguments}'
```

输出:
```json
{
  "tool": "write_file",
  "arguments": {
    "file_path": "test.txt",
    "content": "..."
  }
}
```

---

### 13. 查看 Token 使用统计

```bash
curl -s -X POST http://localhost:8000/api/v1/agent/run \
  -H "Content-Type: application/json" \
  -d '{
    "message": "你好"
  }' | jq '[.logs[] | select(.type == "llm_response")] | {
    total_input: map(.input_tokens) | add,
    total_output: map(.output_tokens) | add
  }'
```

---

## 流式响应（SSE）

### 14. 流式执行任务

```bash
curl -N -X POST http://localhost:8000/api/v1/agent/run-stream \
  -H "Content-Type: application/json" \
  -d '{
    "message": "创建文件 stream_test.txt"
  }'
```

**输出示例**:
```
data: {"type":"step","data":{"step":1,"max_steps":50}}

data: {"type":"content","data":{"delta":"我将"}}

data: {"type":"content","data":{"delta":"创建文件"}}

data: {"type":"tool_call","data":{"tool":"write_file",...}}

data: {"type":"tool_result","data":{"success":true,...}}

data: {"type":"done","data":{"message":"完成"}}
```

---

## 实用的测试脚本

### 快速测试所有功能

运行提供的测试脚本：
```bash
./test_api.sh
```

### 或者使用 watch 监控

```bash
# 持续监控健康状态
watch -n 2 'curl -s http://localhost:8000/health | jq'
```

---

## Python 示例

如果更喜欢用 Python：

```python
import requests

# 基本请求
response = requests.post(
    "http://localhost:8000/api/v1/agent/run",
    json={"message": "创建文件 test.txt"}
)

result = response.json()
print(f"Success: {result['success']}")
print(f"Message: {result['message']}")
print(f"Steps: {result['steps']}")
```

### 使用 httpx（异步）

```python
import asyncio
import httpx

async def test_agent():
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://localhost:8000/api/v1/agent/run",
            json={"message": "你好"}
        )
        result = response.json()
        print(result['message'])

asyncio.run(test_agent())
```

---

## 错误处理示例

### 处理失败的请求

```bash
curl -s -X POST http://localhost:8000/api/v1/agent/run \
  -H "Content-Type: application/json" \
  -d '{
    "message": "执行一个不可能的任务",
    "config": {"max_steps": 1}
  }' | jq '{
    success,
    message,
    error: (if .success == false then .message else null end)
  }'
```

---

## 性能测试

### 使用 ab（Apache Bench）

```bash
# 安装 ab
# macOS: brew install apache2 (已包含)
# Ubuntu: apt-get install apache2-utils

# 并发测试
ab -n 100 -c 10 -p request.json -T application/json \
  http://localhost:8000/api/v1/agent/run
```

**request.json**:
```json
{"message": "你好"}
```

---

## 调试技巧

### 1. 查看完整的 HTTP 响应头

```bash
curl -v -X POST http://localhost:8000/api/v1/agent/run \
  -H "Content-Type: application/json" \
  -d '{"message": "测试"}'
```

### 2. 保存响应到文件

```bash
curl -X POST http://localhost:8000/api/v1/agent/run \
  -H "Content-Type: application/json" \
  -d '{"message": "创建报告"}' \
  -o response.json

# 查看
cat response.json | jq '.'
```

### 3. 使用变量简化测试

```bash
BASE_URL="http://localhost:8000"
API_ENDPOINT="${BASE_URL}/api/v1/agent/run"

# 测试 1
curl -X POST "$API_ENDPOINT" \
  -H "Content-Type: application/json" \
  -d '{"message": "测试1"}'

# 测试 2
curl -X POST "$API_ENDPOINT" \
  -H "Content-Type: application/json" \
  -d '{"message": "测试2"}'
```

---

## 常见问题

### Q: 如何处理包含引号的消息？

```bash
# 使用单引号包裹整个 JSON，内部使用双引号
curl -X POST http://localhost:8000/api/v1/agent/run \
  -H "Content-Type: application/json" \
  -d '{"message": "创建文件 \"my file.txt\""}'

# 或者使用转义
curl -X POST http://localhost:8000/api/v1/agent/run \
  -H "Content-Type: application/json" \
  -d "{\"message\": \"创建文件 \\\"my file.txt\\\"\"}"
```

### Q: 如何查看 API 文档？

访问浏览器：
```
http://localhost:8000/docs
```

---

## 更多示例

查看完整的 API 测试脚本：
```bash
./test_api.sh
```

查看交互式 API 文档：
```
http://localhost:8000/docs
```
