"""Unit tests for the rate limiter."""

import asyncio
import pytest
from app.services.limiter import DownloadLimiter, UserBusyError


@pytest.mark.asyncio
async def test_limiter_single_user_concurrency() -> None:
    limiter = DownloadLimiter(max_concurrent=3)
    user_id = 12345

    async with limiter.throttle(user_id):
        assert limiter.is_user_busy(user_id) is True
        # Second request from same user must raise UserBusyError
        with pytest.raises(UserBusyError):
            async with limiter.throttle(user_id):
                pass

    # After release, user can acquire again
    assert limiter.is_user_busy(user_id) is False
    async with limiter.throttle(user_id):
        assert limiter.is_user_busy(user_id) is True


@pytest.mark.asyncio
async def test_limiter_global_semaphore() -> None:
    limiter = DownloadLimiter(max_concurrent=2)
    active_count = 0
    max_observed = 0

    async def worker(u_id: int):
        nonlocal active_count, max_observed
        async with limiter.throttle(u_id):
            active_count += 1
            max_observed = max(max_observed, active_count)
            await asyncio.sleep(0.05)
            active_count -= 1

    await asyncio.gather(worker(1), worker(2), worker(3), worker(4))
    assert max_observed <= 2
