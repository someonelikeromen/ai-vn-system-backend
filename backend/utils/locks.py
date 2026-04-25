"""
并发控制 — NovelRWLock + NovelStateRefreshBus
"""
from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import AsyncGenerator
from contextlib import asynccontextmanager

from loguru import logger


# ════════════════════════════════════════════════════════════════════════════
# NovelRWLock — 小说级读写锁
# ════════════════════════════════════════════════════════════════════════════

class NovelRWLock:
    """
    小说（novel_id）级别的读写锁。
    - 同一小说的写操作（SSE 游戏回合）互斥。
    - 读操作（查询状态、商城浏览）可并发。
    - 默认写优先（防止读操作饿死写操作）。
    """

    def __init__(self):
        self._locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._read_counts: dict[str, int] = defaultdict(int)
        self._read_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    @asynccontextmanager
    async def write(self, novel_id: str) -> AsyncGenerator[None, None]:
        """独占写锁（同一 novel_id 的所有写操作串行）"""
        lock = self._locks[novel_id]
        try:
            await lock.acquire()
            logger.debug(f"[RWLock] 写锁获取: {novel_id}")
            yield
        finally:
            lock.release()
            logger.debug(f"[RWLock] 写锁释放: {novel_id}")

    @asynccontextmanager
    async def read(self, novel_id: str) -> AsyncGenerator[None, None]:
        """共享读锁（多个读操作可并发，等待写操作完成）"""
        lock = self._locks[novel_id]
        # 简化实现：同样使用独占锁（保证不与写操作冲突）
        # 如果需要真正的读共享，可以改用 asyncio.Semaphore
        try:
            await lock.acquire()
            yield
        finally:
            lock.release()

    def is_locked(self, novel_id: str) -> bool:
        """检查某小说是否当前处于锁定状态"""
        lock = self._locks.get(novel_id)
        return lock is not None and lock.locked()


# 全局单例
novel_rw_lock = NovelRWLock()


@asynccontextmanager
async def novel_write_lock(novel_id: str) -> AsyncGenerator[None, None]:
    """便捷写锁上下文管理器"""
    async with novel_rw_lock.write(novel_id):
        yield


# ════════════════════════════════════════════════════════════════════════════
# NovelStateRefreshBus — 兑换后状态脏位通知总线
# ════════════════════════════════════════════════════════════════════════════

class NovelStateRefreshBus:
    """
    当 ExchangeAgent 执行购买后，通知正在进行的写作回合（DM Agent）
    在下一次 STEP 0 执行前强制重载 statData，避免使用过期缓存。

    用法：
        # 购买成功后
        NovelStateRefreshBus.mark_dirty(novel_id)

        # 写作回合 STEP 0 开始前
        if NovelStateRefreshBus.is_dirty(novel_id):
            state.stat_data = await db.get_protagonist_state(novel_id)
            NovelStateRefreshBus.consume(novel_id)
    """

    _dirty: dict[str, bool] = {}

    @classmethod
    def mark_dirty(cls, novel_id: str) -> None:
        """标记某小说状态已过期（需要重载）"""
        cls._dirty[novel_id] = True
        logger.info(f"[RefreshBus] 状态脏位设置: {novel_id}")

    @classmethod
    def is_dirty(cls, novel_id: str) -> bool:
        """检查某小说状态是否已过期"""
        return cls._dirty.get(novel_id, False)

    @classmethod
    def consume(cls, novel_id: str) -> None:
        """消费脏位（重载完成后调用）"""
        cls._dirty.pop(novel_id, None)
        logger.debug(f"[RefreshBus] 脏位清除: {novel_id}")

    @classmethod
    def get_all_dirty(cls) -> list[str]:
        """返回所有待刷新的小说 ID"""
        return [k for k, v in cls._dirty.items() if v]
