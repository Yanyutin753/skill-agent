"""File-based memory management using AGENTS.md convention.

Implements the AGENTS.md protocol for AI agent memory management.
Each user/session combination has its own AGENTS.md file for isolation.
"""

import shutil
import time
from datetime import datetime
from pathlib import Path
from typing import Optional


class FileMemory:
    """File-based memory using AGENTS.md convention.

    Directory structure:
        ./.agent_memories/{user_id}/{session_id}/AGENTS.md
    """

    def __init__(
        self,
        user_id: str,
        session_id: str,
        base_dir: str = "./.agent_memories",
    ):
        self.user_id = user_id
        self.session_id = session_id
        self.base_dir = Path(base_dir).expanduser()
        self.session_dir = self.base_dir / user_id / session_id
        self.path = self.session_dir / "AGENTS.md"
        self._ensure_dir()

    def _ensure_dir(self) -> None:
        self.session_dir.mkdir(parents=True, exist_ok=True)

    def exists(self) -> bool:
        return self.path.exists()

    def read(self) -> str:
        if not self.path.exists():
            return ""
        return self.path.read_text(encoding="utf-8")

    def write(self, content: str) -> None:
        self.path.write_text(content, encoding="utf-8")

    def delete(self) -> None:
        shutil.rmtree(self.session_dir, ignore_errors=True)

    def init_memory(self, context: str = "") -> str:
        """Initialize a new AGENTS.md file with default structure."""
        now = datetime.now().isoformat(timespec="seconds")
        content = f"""# AGENTS.md

## Meta
- user: {self.user_id}
- session: {self.session_id}
- created: {now}
- updated: {now}

## Context
{context}

## History

## Key Facts

## Notes
"""
        self.write(content)
        return content

    def append_round(
        self,
        round_num: int,
        user_msg: str,
        assistant_msg: str,
        tools_used: Optional[list[str]] = None,
    ) -> None:
        """Append a conversation round to History section."""
        content = self.read()
        if not content:
            content = self.init_memory()

        now = datetime.now().isoformat(timespec="seconds")
        content = self._update_meta_timestamp(content, now)

        tools_str = f"\n**Tools**: {', '.join(tools_used)}" if tools_used else ""

        assistant_truncated = assistant_msg
        if len(assistant_msg) > 500:
            assistant_truncated = assistant_msg[:500] + "..."

        round_text = f"""
### Round {round_num}
**User**: {user_msg}
**Assistant**: {assistant_truncated}{tools_str}
"""
        content = self._insert_before_section(content, "## Key Facts", round_text)
        self.write(content)

    def update_key_facts(self, facts: list[str]) -> None:
        """Update Key Facts section."""
        content = self.read()
        if not content:
            return

        facts_text = "\n".join(f"- {fact}" for fact in facts)
        content = self._replace_section(content, "## Key Facts", facts_text)
        self.write(content)

    def update_context(self, context: str) -> None:
        """Update Context section."""
        content = self.read()
        if not content:
            return

        content = self._replace_section(content, "## Context", context)
        self.write(content)

    def add_note(self, note: str) -> None:
        """Append a note to Notes section."""
        content = self.read()
        if not content:
            return

        now = datetime.now().strftime("%H:%M")
        note_text = f"\n- [{now}] {note}"

        if "## Notes" in content:
            parts = content.split("## Notes")
            content = parts[0] + "## Notes" + parts[1] + note_text

        self.write(content)

    def get_context_for_prompt(self) -> str:
        """Get memory content formatted for injection into system prompt."""
        content = self.read()
        if not content:
            return ""
        return f"<memory>\n{content}\n</memory>"

    def _update_meta_timestamp(self, content: str, timestamp: str) -> str:
        """Update the 'updated' timestamp in Meta section."""
        lines = content.split("\n")
        for i, line in enumerate(lines):
            if line.startswith("- updated:"):
                lines[i] = f"- updated: {timestamp}"
                break
        return "\n".join(lines)

    def _insert_before_section(self, content: str, section: str, text: str) -> str:
        """Insert text before a section header."""
        if section in content:
            return content.replace(section, text + "\n" + section)
        return content + text

    def _replace_section(self, content: str, section: str, new_content: str) -> str:
        """Replace content of a section (until next ## header)."""
        lines = content.split("\n")
        result = []
        in_section = False

        for line in lines:
            if line.startswith(section):
                in_section = True
                result.append(line)
                result.append(new_content)
                continue

            if in_section and line.startswith("## "):
                in_section = False

            if not in_section:
                result.append(line)

        return "\n".join(result)


class FileMemoryManager:
    """Manager for file-based memories with cleanup support."""

    def __init__(self, base_dir: str = "./.agent_memories"):
        self.base_dir = Path(base_dir).expanduser()

    def get_memory(self, user_id: str, session_id: str) -> FileMemory:
        return FileMemory(user_id, session_id, str(self.base_dir))

    def delete_session(self, user_id: str, session_id: str) -> bool:
        session_dir = self.base_dir / user_id / session_id
        if session_dir.exists():
            shutil.rmtree(session_dir)
            return True
        return False

    def delete_user(self, user_id: str) -> bool:
        user_dir = self.base_dir / user_id
        if user_dir.exists():
            shutil.rmtree(user_dir)
            return True
        return False

    def list_sessions(self, user_id: str) -> list[str]:
        user_dir = self.base_dir / user_id
        if not user_dir.exists():
            return []
        return [d.name for d in user_dir.iterdir() if d.is_dir()]

    def list_users(self) -> list[str]:
        if not self.base_dir.exists():
            return []
        return [d.name for d in self.base_dir.iterdir() if d.is_dir()]

    def cleanup_expired(self, max_age_days: int = 7) -> int:
        """Remove sessions older than max_age_days."""
        cutoff = time.time() - (max_age_days * 86400)
        removed = 0

        if not self.base_dir.exists():
            return 0

        for user_dir in self.base_dir.iterdir():
            if not user_dir.is_dir():
                continue
            for session_dir in user_dir.iterdir():
                if not session_dir.is_dir():
                    continue
                agents_md = session_dir / "AGENTS.md"
                if agents_md.exists():
                    mtime = agents_md.stat().st_mtime
                    if mtime < cutoff:
                        shutil.rmtree(session_dir)
                        removed += 1

        return removed

    def get_stats(self) -> dict:
        """Get memory storage statistics."""
        users = self.list_users()
        total_sessions = sum(len(self.list_sessions(u)) for u in users)

        total_size = 0
        if self.base_dir.exists():
            for f in self.base_dir.rglob("AGENTS.md"):
                total_size += f.stat().st_size

        return {
            "total_users": len(users),
            "total_sessions": total_sessions,
            "total_size_kb": round(total_size / 1024, 2),
        }
