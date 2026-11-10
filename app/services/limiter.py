"""Rate limiter providing per-user single active download and global concurrency limit."""

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncIterator, Set
from app.config import settings


class UserBusyError(Exception):
    """Raised when a user already has an active download in progress."""

    pass


class DownloadLimiter:
    """Manages concurrent downloads using per-user flags and a global semaphore."""

    def __init__(self, max_concurrent: int = 3) -> None:
        self._max_concurrent = max_concurrent
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._active_users: Set[int] = set()

    def is_user_busy(self, user_id: int) -> bool:
        """Check if user has an active download."""
        return user_id in self._active_users

    def _acquire_user(self, user_id: int) -> bool:
        """Mark user as active. Returns False if already active."""
        if user_id in self._active_users:
            return False
        self._active_users.add(user_id)
        return True

    def _release_user(self, user_id: int) -> None:
        """Clear user active mark."""
        self._active_users.discard(user_id)

    @asynccontextmanager
    async def throttle(self, user_id: int) -> AsyncIterator[None]:
        """
        Context manager that:
        1. Checks per-user lock (raises UserBusyError if already busy).
        2. Acquires global semaphore slot.
        3. Releases both in finally block.
        """
        if not self._acquire_user(user_id):
            raise UserBusyError()

        try:
            async with self._semaphore:
                yield
        finally:
            self._release_user(user_id)


limiter = DownloadLimiter(max_concurrent=settings.max_concurrent_downloads)
