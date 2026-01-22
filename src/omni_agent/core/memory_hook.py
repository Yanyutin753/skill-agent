"""记忆系统 Hook，集成到 Agent 执行流程"""

import json
from typing import Any, Optional
from omni_agent.core.memory import Memory
from omni_agent.core.hooks import AgentHook, HookContext


EXTRACT_PROMPT = """分析以下对话，提取需要长期记忆的信息。

对话内容：
用户: {user_msg}
助手: {assistant_msg}

提取规则：
1. profile (用户画像): 将用户的职业、背景、技能、偏好、身份等信息合并为一条完整描述
   重要: 同一类型只输出一条记录，将所有相关信息合并
   例如: "用户之前是Java开发，现在从事Python和大模型开发，有女朋友"

2. habit (习惯模式): 用户的工作流程、操作习惯
   例如: "用户习惯先写测试再写代码，项目使用Git Flow"

3. task (当前任务): 当前需要完成的具体任务
   例如: "需要实现快速排序算法"

要求：
- 每种类型最多一条记录，合并同类信息
- 用简洁的一句话概括，不要拆分成多条
- 只提取用户明确提到的信息

返回JSON格式：
{{
  "memories": [
    {{"type": "profile|habit|task", "content": "合并后的完整描述", "importance": 0.5-1.0}}
  ]
}}

如果没有需要记忆的信息，返回: {{"memories": []}}
只返回JSON。"""


class MemoryHook(AgentHook):
    """记忆 Hook，在 Agent 执行前后自动处理记忆

    - before_run: 加载记忆上下文
    - after_run: 保存对话轮次到 session 记忆，并提取 profile/habit/task 记忆
    """

    priority: int = 50

    def __init__(
        self,
        user_id: str,
        session_id: str,
        base_dir: str = "./.agent_memories",
        llm_client: Optional[Any] = None,
    ) -> None:
        self.memory = Memory(user_id, session_id, base_dir)
        self._round_num = 0
        self._last_user_msg = ""
        self._llm_client = llm_client

    async def before_run(self, ctx: HookContext) -> None:
        if not self.memory.exists():
            task = ""
            if hasattr(ctx, "state") and ctx.state.messages:
                for msg in ctx.state.messages:
                    if msg.role == "user":
                        task = msg.content[:200] if msg.content else ""
                        break
            self.memory.init_memory(context=task)

    async def on_step(self, ctx: HookContext, step_data: dict[str, Any]) -> None:
        pass

    async def after_run(self, ctx: HookContext, result: str, success: bool) -> None:
        if not hasattr(ctx, "state"):
            return

        user_msg = ""
        for msg in reversed(ctx.state.messages):
            if msg.role == "user" and msg.content:
                user_msg = msg.content if isinstance(msg.content, str) else str(msg.content)
                break

        if user_msg and user_msg != self._last_user_msg:
            self._round_num += 1
            self._last_user_msg = user_msg

            tools_used = []
            for msg in ctx.state.messages:
                if msg.role == "assistant" and msg.tool_calls:
                    for tc in msg.tool_calls:
                        tools_used.append(tc.function.name)

            self.memory.append_round(
                round_num=self._round_num,
                user_msg=user_msg[:500],
                assistant_msg=result[:500],
                tools_used=tools_used[-5:] if tools_used else None,
            )

            if self._llm_client:
                await self._extract_and_store_memories(user_msg, result)

    async def _extract_and_store_memories(self, user_msg: str, assistant_msg: str) -> None:
        try:
            from omni_agent.schemas.message import Message

            prompt = EXTRACT_PROMPT.format(
                user_msg=user_msg[:500],
                assistant_msg=assistant_msg[:500],
            )

            response = await self._llm_client.generate(
                messages=[Message(role="user", content=prompt)],
                tools=None,
            )

            if not response.content:
                return

            content = response.content.strip()
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
            content = content.strip()

            extracted = json.loads(content)
            memories = extracted.get("memories", [])

            for mem in memories:
                mem_type = mem.get("type")
                mem_content = mem.get("content")
                importance = mem.get("importance", 0.6)

                if not mem_type or not mem_content:
                    continue

                if mem_type == "profile":
                    self.memory.add_profile(
                        content=mem_content,
                        source="extracted",
                        importance=importance,
                    )
                elif mem_type == "habit":
                    self.memory.add_habit(
                        content=mem_content,
                        skill_name="user_pattern",
                        importance=importance,
                    )
                elif mem_type == "task":
                    self.memory.add_task(
                        content=mem_content,
                        category="task",
                        importance=importance,
                    )

        except Exception:
            pass

    def get_context_for_prompt(self) -> str:
        return self.memory.get_context_for_prompt()

    def get_memory(self) -> Memory:
        return self.memory


def create_memory_hook(
    user_id: Optional[str],
    session_id: Optional[str],
    base_dir: str = "./.agent_memories",
    llm_client: Optional[Any] = None,
) -> Optional["MemoryHook"]:
    if not user_id or not session_id:
        return None
    return MemoryHook(user_id, session_id, base_dir, llm_client)
