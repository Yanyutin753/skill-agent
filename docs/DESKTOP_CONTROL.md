# 桌面控制功能文档

## 概述

桌面控制功能允许 Agent 控制计算机桌面，包括截图、鼠标点击、键盘输入等操作。

## 架构设计

```
主 Agent (LLM_MODEL: qwen3-max)
    ↓ 文本决策
调用 vision_agent 工具
    ↓
视觉子 Agent (VISION_MODEL: qwen-vl-max)
    ↓ 执行桌面任务
桌面控制工具
    - desktop_screenshot (截图)
    - desktop_click (点击)
    - desktop_type (输入)
    - desktop_hotkey (快捷键)
    - desktop_find (查找元素)
    - desktop_scroll (滚动)
    - desktop_press_key (按键)
    ↓
返回结果给主 Agent
```

## 配置方式

### 方式 1：同一提供商（推荐）

主模型和视觉模型都使用 DashScope：

```env
# .env
LLM_API_KEY=sk-your-dashscope-key
LLM_MODEL=dashscope/qwen3-max
VISION_MODEL=dashscope/qwen-vl-max
ENABLE_DESKTOP_CONTROL=true
```

### 方式 2：不同提供商

主模型用 OpenAI，视觉模型用 DashScope：

```env
# .env
# 主模型
LLM_API_KEY=sk-your-openai-key
LLM_MODEL=openai/gpt-4o

# 视觉模型
VISION_API_KEY=sk-your-dashscope-key
VISION_API_BASE=https://dashscope.aliyuncs.com/compatible-mode/v1
VISION_MODEL=dashscope/qwen-vl-max

ENABLE_DESKTOP_CONTROL=true
```

### 方式 3：主模型用 DashScope，视觉模型用 OpenAI

```env
# .env
# 主模型
LLM_API_KEY=sk-your-dashscope-key
LLM_API_BASE=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_MODEL=dashscope/qwen3-max

# 视觉模型
VISION_API_KEY=sk-your-openai-key
VISION_MODEL=openai/gpt-4o

ENABLE_DESKTOP_CONTROL=true
```

## 可用工具

### 1. vision_agent（主工具）

调用视觉 Agent 执行复杂桌面任务。

**使用场景：**
- 需要理解屏幕内容
- 多步骤的视觉任务
- 需要验证操作结果

**示例：**
```json
{
  "tool": "vision_agent",
  "parameters": {
    "task": "打开微信并发送消息给张三",
    "max_steps": 15
  }
}
```

### 2. 独立桌面工具

可以直接调用单个工具：

| 工具 | 功能 | 示例 |
|------|------|------|
| desktop_screenshot | 截图 | 查看当前屏幕 |
| desktop_click | 点击 | 点击坐标 (100, 200) |
| desktop_type | 输入 | 输入文字 "Hello" |
| desktop_hotkey | 快捷键 | Cmd+C, Ctrl+V |
| desktop_find | 查找 | 查找"确定"按钮 |
| desktop_scroll | 滚动 | 向下滚动 5 次 |
| desktop_press_key | 按键 | 按回车键 |

## 使用示例

### 示例 1：查看屏幕内容

```bash
curl -X POST http://localhost:8000/api/v1/agent/run \
  -H "Content-Type: application/json" \
  -d '{"message": "帮我看看屏幕上显示了什么"}'
```

**执行流程：**
1. 主 Agent 决定调用 `vision_agent`
2. 视觉 Agent 调用 `desktop_screenshot`
3. 视觉模型理解截图内容
4. 返回描述给主 Agent
5. 主 Agent 回复用户

### 示例 2：打开应用

```bash
curl -X POST http://localhost:8000/api/v1/agent/run \
  -H "Content-Type: application/json" \
  -d '{"message": "打开微信"}'
```

**执行流程：**
1. 主 Agent 调用 `vision_agent`
2. 视觉 Agent 执行：
   - `desktop_hotkey(["command", "space"])` - Spotlight
   - `desktop_type("微信")`
   - `desktop_press_key("return")`
   - `desktop_screenshot()` - 验证是否打开
3. 返回结果

### 示例 3：复杂任务

```bash
curl -X POST http://localhost:8000/api/v1/agent/run \
  -H "Content-Type: application/json" \
  -d '{"message": "帮我打开 Chrome，搜索 Python 教程，并告诉我第一个结果是什么"}'
```

## macOS 权限设置

首次使用需要授予权限：

1. **屏幕录制权限**
   - 系统设置 → 隐私与安全性 → 屏幕录制
   - 添加 Terminal/iTerm

2. **辅助功能权限**
   - 系统设置 → 隐私与安全性 → 辅助功能
   - 添加 Terminal/iTerm

## 故障排除

### 截图失败

**错误：** `Screenshot failed: 'NoneType' object has no attribute 'get_monitors'`

**解决：** 安装依赖
```bash
uv add pillow pyscreeze
```

### 视觉模型未配置

**错误：** `VISION_MODEL not configured`

**解决：** 在 `.env` 中设置
```env
VISION_MODEL=dashscope/qwen-vl-max
```

### API Key 错误

**错误：** `401 Unauthorized`

**解决：** 检查对应模型的 API Key
- 主模型：`LLM_API_KEY`
- 视觉模型：`VISION_API_KEY`（如果不同提供商）

## 最佳实践

1. **使用 vision_agent 处理复杂任务**
   - 多步骤操作
   - 需要视觉反馈的任务

2. **使用独立工具处理简单任务**
   - 单步操作
   - 已知坐标的点击

3. **配置合理的 max_steps**
   - 简单任务：5-10 步
   - 复杂任务：15-20 步

4. **安全注意**
   - 避免执行破坏性操作
   - 谨慎处理敏感信息输入
