"""
API — 记忆图谱调试接口（开发/测试用）
GET /api/memory/{novel_id}/stats        图谱统计
GET /api/memory/{novel_id}/nodes        节点列表（按类型）
POST /api/memory/{novel_id}/recall      手动触发召回
GET /api/memory/queue/stats             提取队列统计
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

router = APIRouter(prefix="/api/memory", tags=["memory"])


@router.get("/{novel_id}/stats")
async def get_memory_stats(novel_id: str):
    """获取记忆图谱统计信息"""
    from memory.graph import graph_manager
    from memory.vector import vector_manager
    from memory.extract_queue import get_extract_queue

    graph_stats = graph_manager.get_stats(novel_id)
    vector_count = await vector_manager.get(novel_id).get_collection_count()
    queue_stats  = get_extract_queue().stats

    return {
        "novel_id":    novel_id,
        "graph":       graph_stats,
        "vector_count": vector_count,
        "queue":       queue_stats,
    }


@router.get("/{novel_id}/nodes")
async def get_memory_nodes(
    novel_id: str,
    node_type: Optional[str] = None,
    world_key: str = "",
):
    """获取记忆节点列表"""
    from memory.graph import graph_manager
    from memory.schema import NodeType

    graph = graph_manager.get(novel_id)

    if node_type:
        try:
            types = [NodeType(node_type)]
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"无效的节点类型: {node_type}，合法值: {[t.value for t in NodeType]}"
            )
        nodes = graph.get_nodes_by_type(types, world_key)
    else:
        nodes = [
            dict(data)
            for _, data in graph._G.nodes(data=True)
            if not world_key or data.get("world_key", "") == world_key
        ]

    nodes.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return {"nodes": nodes[:100], "total": len(nodes)}


class RecallRequest(BaseModel):
    query: str
    world_key: str = ""
    viewer_agent: str = "chronicler"
    top_k: int = 15


@router.post("/{novel_id}/recall")
async def manual_recall(novel_id: str, req: RecallRequest):
    """手动触发混合召回（调试用）"""
    from memory.retriever import hybrid_recall

    result = await hybrid_recall(
        novel_id=novel_id,
        world_key=req.world_key,
        query_text=req.query,
        viewer_agent=req.viewer_agent,
        top_k=req.top_k,
    )
    return {
        "query":    req.query,
        "core_count": len(result.get("core", [])),
        "recalled_count": len(result.get("recalled", [])),
        "result": result,
    }


@router.get("/queue/stats")
async def get_queue_stats():
    """获取后台提取队列状态"""
    from memory.extract_queue import get_extract_queue
    return get_extract_queue().stats
