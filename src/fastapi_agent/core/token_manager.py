"""Token management for message history with automatic summarization."""

from typing import Any

import tiktoken

from fastapi_agent.core.llm_client import LLMClient
from fastapi_agent.schemas.message import Message


class TokenManager:
    """Manages token counting and message history summarization.

    Features:
    - Accurate token counting using tiktoken (cl100k_base encoder)
    - Automatic message history summarization when token limit is exceeded
    - Preserves user messages while summarizing agent execution rounds
    - Fallback to character-based estimation if tiktoken is unavailable
    """

    def __init__(
        self,
        llm_client: LLMClient,
        token_limit: int = 120000,  # Default for claude-3-5-sonnet (200k context)
        enable_summarization: bool = True,
    ):
        """Initialize Token Manager.

        Args:
            llm_client: LLM client for generating summaries
            token_limit: Maximum tokens before triggering summarization
            enable_summarization: Whether to enable automatic summarization
        """
        self.llm = llm_client
        self.token_limit = token_limit
        self.enable_summarization = enable_summarization

        # Initialize tiktoken encoder
        try:
            self.encoding = tiktoken.get_encoding("cl100k_base")
            self.tiktoken_available = True
        except Exception:
            self.encoding = None
            self.tiktoken_available = False

    def estimate_tokens(self, messages: list[Message]) -> int:
        """Accurately calculate token count for message history using tiktoken.

        Uses cl100k_base encoder (GPT-4/Claude/MiniMax compatible).
        Falls back to character-based estimation if tiktoken is unavailable.

        Args:
            messages: List of messages to count tokens for

        Returns:
            Estimated token count
        """
        if not self.tiktoken_available:
            return self._estimate_tokens_fallback(messages)

        total_tokens = 0

        for msg in messages:
            # Count text content
            if isinstance(msg.content, str):
                total_tokens += len(self.encoding.encode(msg.content))
            elif isinstance(msg.content, list):
                for block in msg.content:
                    if isinstance(block, dict):
                        # Convert dict to string for calculation
                        total_tokens += len(self.encoding.encode(str(block)))

            # Count thinking (if present)
            if msg.thinking:
                total_tokens += len(self.encoding.encode(msg.thinking))

            # Count tool_calls (if present)
            if msg.tool_calls:
                total_tokens += len(self.encoding.encode(str(msg.tool_calls)))

            # Metadata overhead per message (approximately 4 tokens)
            total_tokens += 4

        return total_tokens

    def _estimate_tokens_fallback(self, messages: list[Message]) -> int:
        """Fallback token estimation method (when tiktoken is unavailable).

        Uses character-based estimation: ~2.5 characters = 1 token

        Args:
            messages: List of messages to count tokens for

        Returns:
            Estimated token count
        """
        total_chars = 0
        for msg in messages:
            if isinstance(msg.content, str):
                total_chars += len(msg.content)
            elif isinstance(msg.content, list):
                for block in msg.content:
                    if isinstance(block, dict):
                        total_chars += len(str(block))

            if msg.thinking:
                total_chars += len(msg.thinking)

            if msg.tool_calls:
                total_chars += len(str(msg.tool_calls))

        # Rough estimation: average 2.5 characters = 1 token
        return int(total_chars / 2.5)

    async def maybe_summarize_messages(self, messages: list[Message]) -> list[Message]:
        """Summarize message history if token limit is exceeded.

        Strategy (Agent mode):
        - Keep all user messages (these are user intents)
        - Summarize content between each user-user pair (agent execution process)
        - If last round is still executing (has agent/tool messages but no next user), also summarize
        - Structure: system -> user1 -> summary1 -> user2 -> summary2 -> user3 -> summary3 (if executing)

        Args:
            messages: Current message history

        Returns:
            Summarized message history (or original if no summarization needed)
        """
        if not self.enable_summarization:
            return messages

        estimated_tokens = self.estimate_tokens(messages)

        # If not exceeded, no summary needed
        if estimated_tokens <= self.token_limit:
            return messages

        print(f"\n📊 Token estimate: {estimated_tokens}/{self.token_limit}")
        print("🔄 Triggering message history summarization...")

        # Find all user message indices (skip system prompt)
        user_indices = [i for i, msg in enumerate(messages) if msg.role == "user" and i > 0]

        # Need at least 1 user message to perform summary
        if len(user_indices) < 1:
            print("⚠️  Insufficient messages, cannot summarize")
            return messages

        # Build new message list
        new_messages = [messages[0]]  # Keep system prompt
        summary_count = 0

        # Iterate through each user message and summarize the execution process after it
        for i, user_idx in enumerate(user_indices):
            # Add current user message
            new_messages.append(messages[user_idx])

            # Determine message range to summarize
            # If last user, go to end of message list; otherwise to before next user
            if i < len(user_indices) - 1:
                next_user_idx = user_indices[i + 1]
            else:
                next_user_idx = len(messages)

            # Extract execution messages for this round
            execution_messages = messages[user_idx + 1 : next_user_idx]

            # If there are execution messages in this round, summarize them
            if execution_messages:
                summary_text = await self._create_summary(execution_messages, i + 1)
                if summary_text:
                    summary_message = Message(
                        role="user",
                        content=f"[Assistant Execution Summary]\n\n{summary_text}",
                    )
                    new_messages.append(summary_message)
                    summary_count += 1

        new_tokens = self.estimate_tokens(new_messages)
        print(f"✓ Summary completed, tokens reduced from {estimated_tokens} to {new_tokens}")
        print(f"  Structure: system + {len(user_indices)} user messages + {summary_count} summaries")

        return new_messages

    async def _create_summary(self, messages: list[Message], round_num: int) -> str:
        """Create summary for one execution round.

        Args:
            messages: List of messages to summarize
            round_num: Round number

        Returns:
            Summary text
        """
        if not messages:
            return ""

        # Build summary content
        summary_content = f"Round {round_num} execution process:\n\n"
        for msg in messages:
            if msg.role == "assistant":
                content_text = msg.content if isinstance(msg.content, str) else str(msg.content)
                summary_content += f"Assistant: {content_text}\n"
                if msg.tool_calls:
                    tool_names = [tc.function.name for tc in msg.tool_calls]
                    summary_content += f"  → Called tools: {', '.join(tool_names)}\n"
            elif msg.role == "tool":
                result_preview = msg.content if isinstance(msg.content, str) else str(msg.content)
                # Truncate long results
                if len(result_preview) > 500:
                    result_preview = result_preview[:500] + "..."
                summary_content += f"  ← Tool returned: {result_preview}\n"

        # Call LLM to generate concise summary
        try:
            summary_prompt = f"""Please provide a concise summary of the following Agent execution process:

{summary_content}

Requirements:
1. Focus on what tasks were completed and which tools were called
2. Keep key execution results and important findings
3. Be concise and clear, within 1000 words
4. Use English
5. Do not include "user" related content, only summarize the Agent's execution process"""

            summary_msg = Message(role="user", content=summary_prompt)
            response = await self.llm.generate(
                messages=[
                    Message(
                        role="system",
                        content="You are an assistant skilled at summarizing Agent execution processes.",
                    ),
                    summary_msg,
                ]
            )

            return response.content if response.content else ""

        except Exception as e:
            print(f"⚠️  Summary generation failed: {e}")
            # Return simple summary if LLM call fails
            return f"Round {round_num}: Executed {len(messages)} steps (summary generation failed)"
