"""
有界异步提取队列 — 防止记忆提取任务堆积
采用 asyncio.Queue 实现，最大容量由 EXTRACT_QUEUE_MAX 配置控制
"""
from __future__ import annotations

import asyncio
from typing import Optional, Callable
from loguru import logger


class ExtractQueue:
    """
    有界异步记忆提取队列。
    工作模式：生产者（写作回合结束）→ 队列 → 消费者（后台 worker）
    防止大量短回合快速写入导致的提取任务堆积。
    """

    def __init__(self, max_size: int = 50):
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=max_size)
        self._running = False
        self._worker_task: Optional[asyncio.Task] = None
        self._max_size = max_size
        self._dropped = 0     # 丢弃计数（队列满时）
        self._processed = 0   # 已处理计数

    async def start(self) -> None:
        """启动后台消费者 worker"""
        if self._running:
            return
        self._running = True
        self._worker_task = asyncio.create_task(self._worker())
        logger.info(f"[ExtractQueue] 启动（最大容量 {self._max_size}）")

    async def stop(self) -> None:
        """停止队列，等待剩余任务完成"""
        self._running = False
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
        logger.info(
            f"[ExtractQueue] 停止：已处理 {self._processed}，"
            f"丢弃 {self._dropped}"
        )

    def enqueue(self, task: dict) -> bool:
        """
        非阻塞入队。
        task = {
            "novel_id": str,
            "world_key": str,
            "chapter_id": str,
            "messages": list[dict],
            "novel_config": dict,
        }
        Returns: True=入队成功, False=队列已满（任务被丢弃）
        """
        try:
            self._queue.put_nowait(task)
            return True
        except asyncio.QueueFull:
            self._dropped += 1
            logger.warning(
                f"[ExtractQueue] 队列已满（{self._max_size}），"
                f"丢弃任务 novel_id={task.get('novel_id','?')[:8]}，"
                f"累计丢弃 {self._dropped}"
            )
            return False

    async def _worker(self) -> None:
        """后台消费者循环"""
        from memory.extractor import memory_extractor

        while self._running:
            try:
                task = await asyncio.wait_for(
                    self._queue.get(), timeout=5.0
                )
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break

            try:
                novel_id   = task.get("novel_id", "")
                world_key  = task.get("world_key", "")
                chapter_id = task.get("chapter_id", "")
                messages   = task.get("messages", [])
                config     = task.get("novel_config", {})

                created = await memory_extractor.extract_and_persist(
                    novel_id=novel_id,
                    world_key=world_key,
                    chapter_id=chapter_id,
                    new_messages=messages,
                    novel_config=config,
                )
                self._processed += 1
                logger.debug(
                    f"[ExtractQueue] 完成 novel={novel_id[:8]}, "
                    f"新节点={len(created)}, 队列剩余={self._queue.qsize()}"
                )
            except Exception as e:
                logger.error(f"[ExtractQueue] 提取任务异常: {e}")
            finally:
                self._queue.task_done()

    @property
    def queue_size(self) -> int:
        return self._queue.qsize()

    @property
    def stats(self) -> dict:
        return {
            "queue_size":   self._queue.qsize(),
            "max_size":     self._max_size,
            "processed":    self._processed,
            "dropped":      self._dropped,
            "running":      self._running,
        }


# ── 全局单例 ──────────────────────────────────────────────────────────────
_extract_queue: Optional[ExtractQueue] = None


def get_extract_queue() -> ExtractQueue:
    global _extract_queue
    if _extract_queue is None:
        from config import get_settings
        s = get_settings()
        _extract_queue = ExtractQueue(max_size=s.extract_queue_max)
    return _extract_queue
