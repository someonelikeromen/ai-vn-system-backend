"""
SSE 游戏主路由 — POST /api/sessions/{novel_id}/message
返回完整 SSE 流（text/event-stream）
"""
from __future__ import annotations

import asyncio
import json
from typing import AsyncGenerator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from agents.state import (
    AgentState, SSEEventType, sse_event, empty_state, push_sse
)
from utils.locks import novel_write_lock

router = APIRouter(prefix="/api/sessions", tags=["game"])


class MessageRequest(BaseModel):
    user_input: str
    chapter_id: str = ""


@router.post("/{novel_id}/message")
async def send_message(novel_id: str, req: MessageRequest):
    """
    发起一次写作回合，返回 SSE 流。
    前端使用 EventSource 或 fetch + ReadableStream 消费。
    """
    from db.queries import get_db
    db = get_db()

    # 验证小说存在
    novel = await db.get_novel(novel_id)
    if not novel:
        raise HTTPException(status_code=404, detail="小说不存在")

    protagonist = await db.get_protagonist_state(novel_id)
    if not protagonist:
        raise HTTPException(status_code=400, detail="主角未初始化，请先调用 /init")

    world_key  = novel.get("current_world_key", "")
    chapter_id = req.chapter_id or f"runtime_{novel_id[:8]}"

    async def event_generator() -> AsyncGenerator[str, None]:
        # SSE 队列（无限大，避免 Agent 阻塞）
        sse_queue: asyncio.Queue[str] = asyncio.Queue(maxsize=500)

        # 构建初始状态
        state = empty_state(
            novel_id=novel_id,
            user_input=req.user_input,
            chapter_id=chapter_id,
            world_key=world_key,
            sse_queue=sse_queue,
        )

        async def run_graph():
            from agents.graph import get_writing_app
            app = get_writing_app()
            try:
                async with novel_write_lock(novel_id):
                    final = await app.ainvoke(state)
                    # 发送完成事件
                    done_data = {
                        "chapter_id":      final.get("chapter_id", ""),
                        "purity_passed":   final.get("purity_result", {}).get("passed", True),
                        "grants_count":    len(final.get("system_grants", [])),
                        "growth_count":    len(final.get("growth_results", [])),
                        "calibration":     final.get("calibration_result", {}),
                    }
                    await sse_queue.put(
                        sse_event(SSEEventType.DONE, **done_data)
                    )
            except Exception as e:
                await sse_queue.put(
                    sse_event(SSEEventType.ERROR, content=str(e))
                )
                await sse_queue.put(
                    sse_event(SSEEventType.DONE, error=True)
                )

        # 在后台启动图执行
        graph_task = asyncio.create_task(run_graph())

        # 消费 SSE 队列并 yield
        while True:
            try:
                item = await asyncio.wait_for(sse_queue.get(), timeout=120.0)
                yield item
                sse_queue.task_done()

                # 检测完成（解析 JSON 而非字符串匹配）
                is_done = False
                try:
                    parsed = json.loads(item.removeprefix("data: ").strip())
                    is_done = parsed.get("type") == "done"
                except Exception:
                    pass
                if is_done:
                    break
            except asyncio.TimeoutError:
                # 发送心跳（防止代理超时断开）
                yield ": heartbeat\n\n"
            except asyncio.CancelledError:
                graph_task.cancel()
                break


        # 确保图任务完成
        if not graph_task.done():
            graph_task.cancel()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control":   "no-cache",
            "X-Accel-Buffering": "no",
            "Connection":      "keep-alive",
        },
    )


@router.get("/{novel_id}/messages")
async def get_messages(novel_id: str, limit: int = 50):
    """获取最近的消息历史"""
    from db.queries import get_db
    db = get_db()
    msgs = await db.get_messages(novel_id, limit=limit)
    return {"messages": msgs, "count": len(msgs)}


@router.get("/{novel_id}/status")
async def get_session_status(novel_id: str):
    """获取当前会话状态"""
    from db.queries import get_db
    from utils.locks import novel_rw_lock
    db = get_db()

    protagonist = await db.get_protagonist_state(novel_id)
    active_hooks = await db.get_active_hooks(novel_id)

    return {
        "novel_id":     novel_id,
        "is_locked":    novel_rw_lock.is_locked(novel_id),
        "protagonist":  protagonist,
        "hooks_count":  len(active_hooks),
    }


@router.get("/{novel_id}/rollback/snapshots")
async def list_rollback_snapshots(novel_id: str, limit: int = 3):
    """列出最近 N 条可回滚的快照（含消息摘要）"""
    from db.queries import get_db
    db = get_db()
    novel = await db.get_novel(novel_id)
    if not novel:
        raise HTTPException(status_code=404, detail="小说不存在")

    snapshots = await db.get_recent_turn_snapshots(novel_id, limit=min(limit, 5))
    return {"snapshots": snapshots, "count": len(snapshots)}


@router.post("/{novel_id}/rollback/{snapshot_id}")
async def rollback_turn(novel_id: str, snapshot_id: str):
    """
    完整回滚到指定快照（七层数据）：
    - protagonist_state / medals / growth_records / hooks / messages / snapshots
    - 记忆图谱节点（NetworkX + ChromaDB）
    """
    from db.queries import get_db
    from utils.locks import novel_write_lock
    from memory.rollback import memory_rollback
    db = get_db()
    novel = await db.get_novel(novel_id)
    if not novel:
        raise HTTPException(status_code=404, detail="小说不存在")

    async with novel_write_lock(novel_id):
        result = await db.rollback_to_snapshot(novel_id, snapshot_id)

    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])

    # 记忆图谱清理（按快照时间戳）
    mem_result = {"graph_removed": 0, "vector_removed": 0}
    snap_time = result.get("snapshot_created_at", "")
    if snap_time:
        try:
            mem_result = await memory_rollback.rollback_by_time(novel_id, snap_time)
        except Exception as e:
            mem_result = {"graph_removed": 0, "vector_removed": 0, "error": str(e)}

    return {
        "message":            f"已回滚到第 {result['restored_to_order']} 条消息之前",
        "deleted_messages":   result["deleted_messages"],
        "medals_restored":    result.get("medals_restored", 0),
        "growth_restored":    result.get("growth_restored", 0),
        "graph_removed":      mem_result.get("graph_removed", 0),
        "vector_removed":     mem_result.get("vector_removed", 0),
        "snapshot_id":        result["snapshot_id"],
        "protagonist_name":   result["protagonist_name"],
        "protagonist_points": result["protagonist_points"],
    }
