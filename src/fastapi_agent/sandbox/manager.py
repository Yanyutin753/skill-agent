"""Sandbox lifecycle manager - one sandbox per session."""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional
from uuid import uuid4

logger = logging.getLogger(__name__)


@dataclass
class SandboxInstance:
    """Represents a sandbox instance for a session."""

    session_id: str
    sandbox_id: str = field(default_factory=lambda: str(uuid4()))
    base_url: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    last_accessed: datetime = field(default_factory=datetime.now)
    _client: Any = field(default=None, repr=False)

    @property
    def client(self) -> Any:
        if self._client is None:
            raise RuntimeError("Sandbox client not initialized")
        return self._client

    def touch(self) -> None:
        self.last_accessed = datetime.now()

    @property
    def home_dir(self) -> str:
        if self._client:
            return self._client.sandbox.get_context().home_dir
        return "/home/user"


class SandboxManager:
    """Manages sandbox instances per session.

    Features:
    - One sandbox per session_id
    - Auto-create sandbox on first access
    - TTL-based cleanup for idle sandboxes
    - Async-safe with locks

    Usage:
        manager = SandboxManager(base_url="http://localhost:8080")

        # Get or create sandbox for session
        sandbox = await manager.get_sandbox("session-123")

        # Execute commands
        result = sandbox.client.shell.exec_command(command="ls -la")

        # Cleanup when done
        await manager.remove_sandbox("session-123")
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8080",
        auto_start_docker: bool = False,
        docker_image: str = "ghcr.io/agent-infra/sandbox:latest",
        ttl_seconds: int = 3600,
        max_sandboxes: int = 100,
    ) -> None:
        self._base_url = base_url
        self._auto_start_docker = auto_start_docker
        self._docker_image = docker_image
        self._ttl_seconds = ttl_seconds
        self._max_sandboxes = max_sandboxes

        self._sandboxes: dict[str, SandboxInstance] = {}
        self._lock = asyncio.Lock()
        self._initialized = False
        self._docker_container_id: Optional[str] = None

    async def initialize(self) -> None:
        """Initialize the sandbox manager."""
        if self._initialized:
            return

        if self._auto_start_docker:
            await self._start_docker_container()

        self._initialized = True
        logger.info(f"SandboxManager initialized, base_url={self._base_url}")

    async def _start_docker_container(self) -> None:
        """Start sandbox Docker container if not running."""
        import subprocess

        try:
            result = subprocess.run(
                ["docker", "ps", "-q", "-f", f"ancestor={self._docker_image}"],
                capture_output=True,
                text=True,
            )
            if result.stdout.strip():
                self._docker_container_id = result.stdout.strip().split("\n")[0]
                logger.info(f"Using existing sandbox container: {self._docker_container_id}")
                return

            logger.info(f"Starting sandbox container: {self._docker_image}")
            result = subprocess.run(
                [
                    "docker", "run", "-d",
                    "--security-opt", "seccomp=unconfined",
                    "-p", "8080:8080",
                    self._docker_image,
                ],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                self._docker_container_id = result.stdout.strip()
                logger.info(f"Started sandbox container: {self._docker_container_id}")
                await asyncio.sleep(3)
            else:
                logger.error(f"Failed to start container: {result.stderr}")
        except Exception as e:
            logger.error(f"Docker startup failed: {e}")

    async def get_sandbox(self, session_id: str) -> SandboxInstance:
        """Get or create sandbox for session.

        Args:
            session_id: Session identifier

        Returns:
            SandboxInstance for the session
        """
        async with self._lock:
            if session_id in self._sandboxes:
                sandbox = self._sandboxes[session_id]
                sandbox.touch()
                return sandbox

            if len(self._sandboxes) >= self._max_sandboxes:
                await self._cleanup_oldest()

            sandbox = await self._create_sandbox(session_id)
            self._sandboxes[session_id] = sandbox
            return sandbox

    async def _create_sandbox(self, session_id: str) -> SandboxInstance:
        """Create a new sandbox instance."""
        try:
            from agent_sandbox import Sandbox
        except ImportError:
            raise RuntimeError(
                "agent-sandbox not installed. Run: uv add agent-sandbox"
            )

        client = Sandbox(base_url=self._base_url)

        sandbox = SandboxInstance(
            session_id=session_id,
            base_url=self._base_url,
            _client=client,
        )

        logger.info(f"Created sandbox for session: {session_id}")
        return sandbox

    async def remove_sandbox(self, session_id: str) -> bool:
        """Remove sandbox for session.

        Args:
            session_id: Session identifier

        Returns:
            True if removed, False if not found
        """
        async with self._lock:
            if session_id not in self._sandboxes:
                return False

            del self._sandboxes[session_id]
            logger.info(f"Removed sandbox for session: {session_id}")
            return True

    async def _cleanup_oldest(self) -> None:
        """Remove the oldest sandbox to make room."""
        if not self._sandboxes:
            return

        oldest_session = min(
            self._sandboxes.keys(),
            key=lambda k: self._sandboxes[k].last_accessed,
        )
        del self._sandboxes[oldest_session]
        logger.info(f"Cleaned up oldest sandbox: {oldest_session}")

    async def cleanup_expired(self) -> int:
        """Remove sandboxes that have exceeded TTL.

        Returns:
            Number of sandboxes removed
        """
        async with self._lock:
            now = datetime.now()
            expired = [
                session_id
                for session_id, sandbox in self._sandboxes.items()
                if (now - sandbox.last_accessed).total_seconds() > self._ttl_seconds
            ]

            for session_id in expired:
                del self._sandboxes[session_id]

            if expired:
                logger.info(f"Cleaned up {len(expired)} expired sandboxes")

            return len(expired)

    async def shutdown(self) -> None:
        """Shutdown manager and cleanup resources."""
        async with self._lock:
            self._sandboxes.clear()

        if self._docker_container_id and self._auto_start_docker:
            import subprocess
            try:
                subprocess.run(
                    ["docker", "stop", self._docker_container_id],
                    capture_output=True,
                )
                logger.info(f"Stopped sandbox container: {self._docker_container_id}")
            except Exception as e:
                logger.error(f"Failed to stop container: {e}")

        self._initialized = False
        logger.info("SandboxManager shutdown complete")

    @property
    def active_sandboxes(self) -> int:
        return len(self._sandboxes)

    def get_stats(self) -> dict[str, Any]:
        return {
            "active_sandboxes": self.active_sandboxes,
            "max_sandboxes": self._max_sandboxes,
            "ttl_seconds": self._ttl_seconds,
            "base_url": self._base_url,
        }
