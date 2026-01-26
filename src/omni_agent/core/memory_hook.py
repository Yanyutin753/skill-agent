"""记忆系统 Hook，集成到 Agent 执行流程，支持向量去重。"""

import json
import logging
import uuid
from typing import Any, Callable, Optional

from omni_agent.core.memory import Memory
from omni_agent.core.memory_vector import MemoryVectorStore
from omni_agent.core.hooks import AgentHook, HookContext

logger = logging.getLogger(__name__)

EXTRACT_PROMPT = """分析以下对话，提取需要长期记忆的信息。

对话内容：
用户: {user_msg}
助手: {assistant_msg}

当前活跃任务：
{active_tasks}

提取规则：
1. profile (用户画像): 将用户的职业、背景、技能、偏好、身份等信息合并为一条完整描述
   例如: "用户是Python开发者，偏好简洁代码风格"

2. habit (习惯模式): 用户的工作流程、操作习惯
   例如: "用户习惯先写测试再写代码"

3. task (当前任务): 用户新提出的具体任务
   例如: "需要实现二叉树中序遍历算法"

4. completed_tasks: 根据对话判断哪些活跃任务已完成
   - 如果助手成功完成了某个任务，将该任务内容加入此列表

要求：
- 每种类型最多一条记录
- 用简洁的一句话概括
- 只提取明确提到的信息
- 认真判断任务是否已完成

返回JSON格式：
{{
  "memories": [
    {{"type": "profile|habit|task", "content": "描述", "importance": 0.5-1.0}}
  ],
  "completed_tasks": ["已完成的任务内容1", "已完成的任务内容2"]
}}

如果没有需要记忆的信息，返回: {{"memories": [], "completed_tasks": []}}
只返回JSON。"""


class MemoryHook(AgentHook):
    """记忆 Hook，在 Agent 执行前后自动处理记忆。

    - before_run: 加载记忆上下文
    - after_run: 保存对话轮次到 session 记忆，并提取 profile/habit/task 记忆
    - 向量去重: 新记忆存入前检索相似记忆，避免重复（存储在 PostgreSQL）
    """

    priority: int = 50
    SIMILARITY_THRESHOLD: float = 0.75

    def __init__(
        self,
        user_id: str,
        session_id: str,
        base_dir: str = "./.agent_memories",
        llm_client: Optional[Any] = None,
        enable_vector_dedup: bool = True,
    ) -> None:
        self.memory = Memory(user_id, session_id, base_dir)
        self._user_id = user_id
        self._session_id = session_id
        self._round_num = 0
        self._last_user_msg = ""
        self._llm_client = llm_client
        self._enable_vector_dedup = enable_vector_dedup
        self._embedding_service: Optional[Any] = None
        self._vector_store: Optional[MemoryVectorStore] = None

    def _get_embedding_service(self) -> Optional[Any]:
        """延迟加载 embedding 服务。"""
        if self._embedding_service is None and self._enable_vector_dedup:
            try:
                from omni_agent.rag.embedding_service import embedding_service
                self._embedding_service = embedding_service
            except Exception as e:
                logger.warning(f"Failed to load embedding service: {e}")
                self._enable_vector_dedup = False
        return self._embedding_service

    def _get_vector_store(self) -> Optional[MemoryVectorStore]:
        """延迟加载向量存储。"""
        if self._vector_store is None and self._enable_vector_dedup:
            try:
                self._vector_store = MemoryVectorStore(self._user_id, self._session_id)
            except Exception as e:
                logger.warning(f"Failed to create vector store: {e}")
                self._enable_vector_dedup = False
        return self._vector_store

    async def before_run(self, ctx: HookContext) -> None:
        if not self.memory.exists():
            task = ""
            if hasattr(ctx, "state") and ctx.state.messages:
                for msg in ctx.state.messages:
                    if msg.role == "user":
                        content = msg.content
                        if isinstance(content, str):
                            task = content[:200]
                        break
            self.memory.init_memory(context=task)

    async def on_step(self, ctx: HookContext, step_data: dict[str, Any]) -> None:
        pass

    async def after_run(self, ctx: HookContext, result: str, success: bool) -> None:
        logger.info(f"MemoryHook.after_run called, success={success}")
        if not hasattr(ctx, "state"):
            logger.warning("MemoryHook: ctx has no state")
            return

        user_msg = ""
        for msg in reversed(ctx.state.messages):
            if msg.role == "user" and msg.content:
                user_msg = msg.content if isinstance(msg.content, str) else str(msg.content)
                break

        logger.info(f"MemoryHook: user_msg={user_msg[:50]}..., last_user_msg={self._last_user_msg[:50] if self._last_user_msg else ''}")

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
            logger.info(f"MemoryHook: appended round {self._round_num}")

            if self._llm_client:
                logger.info("MemoryHook: calling _extract_and_store_memories")
                await self._extract_and_store_memories(user_msg, result)
            else:
                logger.warning("MemoryHook: _llm_client is None, skipping extraction")

            if self.memory.needs_compression():
                self.memory.compress()

    async def _check_and_store_memory(
        self,
        memory_id: str,
        content: str,
        memory_type: str,
        store_func: Callable[..., None],
        **kwargs: Any,
    ) -> bool:
        """检查相似度并存储记忆。

        Returns:
            True 如果是新记忆，False 如果是重复记忆
        """
        embedding_service = self._get_embedding_service()
        vector_store = self._get_vector_store()

        if embedding_service and vector_store and self._enable_vector_dedup:
            try:
                embedding = await embedding_service.embed_text(content)

                similar = await vector_store.find_similar(
                    embedding=embedding,
                    memory_type=memory_type,
                    threshold=self.SIMILARITY_THRESHOLD,
                    top_k=1,
                )

                if similar:
                    existing_id, sim, existing_content = similar[0]
                    logger.debug(
                        f"Found similar {memory_type} memory (sim={sim:.2f}): "
                        f"'{existing_content[:50]}...' ~ '{content[:50]}...'"
                    )
                    return False

                store_func(content=content, **kwargs)
                await vector_store.add(memory_id, content, memory_type, embedding)
                return True

            except Exception as e:
                logger.warning(f"Vector dedup failed, falling back to direct store: {e}")

        store_func(content=content, **kwargs)
        return True

    async def _extract_and_store_memories(self, user_msg: str, assistant_msg: str) -> None:
        try:
            from omni_agent.schemas.message import Message

            logger.info("_extract_and_store_memories: starting extraction")
            active_tasks = self.memory.get_memories("task")
            active_task_list = [
                t.get("content", "")
                for t in active_tasks
                if t.get("metadata", {}).get("status") != "completed"
            ]
            active_tasks_str = "\n".join(f"- {t}" for t in active_task_list) if active_task_list else "无"
            logger.info(f"_extract_and_store_memories: active_tasks={active_tasks_str[:100]}")

            prompt = EXTRACT_PROMPT.format(
                user_msg=user_msg[:500],
                assistant_msg=assistant_msg[:500],
                active_tasks=active_tasks_str,
            )

            logger.info("_extract_and_store_memories: calling LLM")
            response = await self._llm_client.generate(
                messages=[Message(role="user", content=prompt)],
                tools=None,
            )

            if not response.content:
                logger.warning("_extract_and_store_memories: empty response from LLM")
                return

            content = response.content.strip()
            logger.info(f"_extract_and_store_memories: LLM response={content[:200]}")
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
            content = content.strip()

            extracted = json.loads(content)
            memories = extracted.get("memories", [])
            logger.info(f"_extract_and_store_memories: extracted {len(memories)} memories")

            completed_tasks = extracted.get("completed_tasks", [])
            for completed_content in completed_tasks:
                for task in active_tasks:
                    task_content = task.get("content", "")
                    if task_content and completed_content in task_content:
                        task_id = task.get("id")
                        if task_id:
                            self.memory.update_task_status(task_id, "completed")
                            logger.debug(f"Marked task as completed: {task_content[:50]}")

            for mem in memories:
                mem_type = mem.get("type")
                mem_content = mem.get("content")
                importance = mem.get("importance", 0.6)

                if not mem_type or not mem_content:
                    continue

                memory_id = str(uuid.uuid4())[:12]

                if mem_type == "profile":
                    await self._check_and_store_memory(
                        memory_id=memory_id,
                        content=mem_content,
                        memory_type="profile",
                        store_func=self.memory.add_profile,
                        source="extracted",
                        importance=importance,
                    )
                elif mem_type == "habit":
                    await self._check_and_store_memory(
                        memory_id=memory_id,
                        content=mem_content,
                        memory_type="habit",
                        store_func=self.memory.add_habit,
                        skill_name="user_pattern",
                        importance=importance,
                    )
                elif mem_type == "task":
                    await self._check_and_store_memory(
                        memory_id=memory_id,
                        content=mem_content,
                        memory_type="task",
                        store_func=self.memory.add_task,
                        category="task",
                        importance=importance,
                    )

        except Exception as e:
            logger.debug(f"Failed to extract memories: {e}")

    def get_context_for_prompt(self) -> str:
        return self.memory.get_context_for_prompt()

    def get_memory(self) -> Memory:
        return self.memory


def create_memory_hook(
    user_id: Optional[str],
    session_id: Optional[str],
    base_dir: str = "./.agent_memories",
    llm_client: Optional[Any] = None,
    enable_vector_dedup: bool = True,
) -> Optional["MemoryHook"]:
    if not user_id or not session_id:
        return None
    return MemoryHook(
        user_id,
        session_id,
        base_dir,
        llm_client,
        enable_vector_dedup,
    )
