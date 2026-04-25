"""
LangGraph 主写作状态机 — 5步工作流编排
"""
from __future__ import annotations

import asyncio
from langgraph.graph import StateGraph, END
from agents.state import AgentState, WorkflowStep


# ── 各 Agent 节点函数 ──────────────────────────────────────────────────────

async def dm_node(state: AgentState) -> AgentState:
    from agents.dm import run_dm
    return await run_dm(state)


async def npc_sandbox_node(state: AgentState) -> AgentState:
    """NPC + Sandbox 并发执行（各自使用 state 副本，避免数据竞争）"""
    from agents.npc import run_npc_actors
    from agents.calibrator import run_sandbox
    import copy

    # 两个任务各自使用当前state的浅副本，避免分支引用相互覆盖
    npc_state     = {k: v for k, v in state.items()}
    sandbox_state = {k: v for k, v in state.items()}

    npc_task     = asyncio.create_task(run_npc_actors(npc_state))
    sandbox_task = asyncio.create_task(run_sandbox(sandbox_state))
    npc_result, sandbox_result = await asyncio.gather(npc_task, sandbox_task, return_exceptions=True)

    # 良性合并：只提取各自负责的字段（避免整dict.update覆盖）
    if isinstance(npc_result, dict):
        state["npc_responses"] = npc_result.get("npc_responses", [])
    if isinstance(sandbox_result, dict):
        # run_sandbox 把推演结果写到 state["sandbox_result"]，返回的是整个 state
        state["sandbox_result"] = sandbox_result.get("sandbox_result", {})
        # 如沙盒建议切换场景类型，同步到主 state
        if sandbox_result.get("scene_type") and sandbox_result["scene_type"] != "normal":
            state["scene_type"] = sandbox_result["scene_type"]
    return state


async def style_node(state: AgentState) -> AgentState:
    from agents.npc import run_style_director
    return await run_style_director(state)


async def chronicler_node(state: AgentState) -> AgentState:
    from agents.chronicler import run_chronicler
    return await run_chronicler(state)


async def calibrator_node(state: AgentState) -> AgentState:
    from agents.calibrator import run_calibrator
    return await run_calibrator(state)


async def planner_node(state: AgentState) -> AgentState:
    from agents.calibrator import run_planner
    return await run_planner(state)


async def archiver_node(state: AgentState) -> AgentState:
    from agents.calibrator import run_archiver
    return await run_archiver(state)


# ── 条件边 ────────────────────────────────────────────────────────────────

def should_abort(state: AgentState) -> str:
    """DM 验证后的路由：abort → end, pass → continue"""
    if state.get("should_abort"):
        return "abort"
    return "continue"



# ════════════════════════════════════════════════════════════════════════════
# 构建 LangGraph 状态机
# ════════════════════════════════════════════════════════════════════════════

def build_writing_graph() -> StateGraph:
    """构建并返回主写作状态机（编译前）"""
    g = StateGraph(AgentState)

    g.add_node("dm",         dm_node)
    g.add_node("world",      npc_sandbox_node)
    g.add_node("style",      style_node)
    g.add_node("chronicler", chronicler_node)
    g.add_node("calibrator", calibrator_node)
    g.add_node("planner",    planner_node)
    g.add_node("archiver",   archiver_node)

    g.set_entry_point("dm")

    g.add_conditional_edges("dm", should_abort, {
        "abort":    END,
        "continue": "world",
    })
    g.add_edge("world",      "style")
    g.add_edge("style",      "chronicler")
    g.add_edge("chronicler", "calibrator")
    g.add_edge("calibrator", "planner")
    g.add_edge("planner",    "archiver")
    g.add_edge("archiver",   END)

    return g


# 编译好的图（全局单例）
_writing_app = None

def get_writing_app():
    global _writing_app
    if _writing_app is None:
        _writing_app = build_writing_graph().compile()
    return _writing_app
