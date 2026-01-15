"""Retry logic for API calls with exponential backoff."""

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Callable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


@dataclass
class RetryConfig:
    """Configuration for retry logic."""

    enabled: bool = True
    max_retries: int = 3
    initial_delay: float = 1.0  # Initial delay in seconds
    max_delay: float = 60.0  # Maximum delay in seconds
    exponential_base: float = 2.0  # Exponential backoff multiplier
    jitter: bool = True  # Add random jitter to avoid thundering herd


def async_retry(
    config: RetryConfig,
    on_retry: Callable[[int, Exception], None] | None = None,
) -> Callable:
    """Decorator for retrying async functions with exponential backoff.

    Args:
        config: Retry configuration
        on_retry: Optional callback function called on each retry
                 Receives (retry_count, exception) as arguments

    Returns:
        Decorated function with retry logic
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exception = None

            for attempt in range(config.max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_exception = e

                    # Don't retry on last attempt
                    if attempt == config.max_retries:
                        break

                    # Call retry callback if provided
                    if on_retry:
                        on_retry(attempt + 1, e)

                    # Calculate delay with exponential backoff
                    delay = min(
                        config.initial_delay * (config.exponential_base**attempt),
                        config.max_delay,
                    )

                    # Add jitter if enabled
                    if config.jitter:
                        import random

                        delay = delay * (0.5 + random.random() * 0.5)

                    logger.warning(
                        f"Retry {attempt + 1}/{config.max_retries} after {delay:.2f}s: {e}"
                    )

                    await asyncio.sleep(delay)

            # All retries exhausted
            raise last_exception  # type: ignore

        return wrapper

    return decorator
