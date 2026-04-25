"""
AgentState — LangGraph 主写作状态机的状态类型定义
SSEEvent — SSE 流事件格式
"""
from __future__ import annotations

import asyncio
from enum import Enum
from typing import Any, Optional, TypedDict, Annotated
import operator


# ════════════════════════════════════════════════════════════════════════════
# SSE 事件类型
# ════════════════════════════════════════════════════════════════════════════

class SSEEventType(str, Enum):
    LOG          = "log"          # 工作流步骤日志（前端左侧边栏）
    THOUGHT      = "thought"      # Agent 推理过程（折叠显示）
    NOVEL_TEXT   = "novel_text"   # 正文文字流（主区域实时打字）
    SYSTEM_GRANT = "system_grant" # 数值结算标签
    ERROR        = "error"        # 错误信息
    DONE         = "done"         # 回合结束


def sse_event(event_type: SSEEventType, **payload) -> str:
    """格式化 SSE 数据行"""
    import json
    data = {"type": event_type.value, **payload}
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


# ════════════════════════════════════════════════════════════════════════════
# WorkflowStep 枚举（对应 WORKFLOW.md 5步铁律）
# ════════════════════════════════════════════════════════════════════════════

class WorkflowStep(int, Enum):
    STATE_READ       = 0   # STEP 0: 状态读取（DM）
    CONSISTENCY      = 1   # STEP 1: 一致性验证（DM）
    WORLD_CHECK      = 2   # STEP 2: 世界/叙事验证（Sandbox+NPC）
    WRITING          = 3   # STEP 3: 正文创作（StyleDirector+Chronicler）
    ARCHIVING        = 4   # STEP 4: 归档结算（Calibrator+Planner+Archiver）


# ════════════════════════════════════════════════════════════════════════════
# AgentState — LangGraph TypedDict
# ════════════════════════════════════════════════════════════════════════════

class AgentState(TypedDict, total=False):
    """
    LangGraph 主写作状态机的共享状态。
    每个 Node 读取、更新这个状态，最终输出给 SSE 端点。
    """

    # ── 会话标识 ────────────────────────────────────────────────────────────
    novel_id:      str
    world_key:     str
    chapter_id:    str

    # ── 当前轮输入 ───────────────────────────────────────────────────────────
    user_input:    str

    # ── 主角状态（STEP 0 读取，整轮只读）──────────────────────────────────────
    stat_data:     dict          # protagonist_state 完整字典
    owned_items:   list[dict]    # 持有物品列表
    medals:        dict          # {stars: count}
    char_points:   int           # 积分余额

    # ── DM 验证结果（STEP 0+1 输出）─────────────────────────────────────────
    dm_verdict:    str           # "pass" | "reject" | "modify"
    dm_feedback:   str           # 拒绝/修正说明
    dm_modified_input: str       # DM 修正后的用户输入（仅 modify 时）
    scene_type:    str           # "normal" | "combat" | "dialogue"
    world_context: dict          # 世界档案/时间流速/限时商品

    # ── 记忆召回结果（STEP 1 DM 四层检索）───────────────────────────────────
    memory_context: dict         # {"core": [...], "recalled": [...]}

    # ── NPC 响应（STEP 2 并发）───────────────────────────────────────────────
    active_npcs:    list[str]    # 当前场景活跃的 NPC 名称列表
    npc_responses:  list[dict]   # [{npc_name, thought, planned_action, dialogue}]

    # ── Sandbox 推演结果（STEP 2）────────────────────────────────────────────
    sandbox_result: dict         # {causal_chain, expected_consequences, warnings}

    # ── 文风选取（STEP 3 StyleDirector）──────────────────────────────────────
    style_stack:   list[str]     # 选取的文风原子 ID 列表（如 "零度写作", "节奏大师"）
    style_content: str           # 从文风文件加载的完整文风说明文本

    # ── 正文生成（STEP 3 Chronicler）────────────────────────────────────────
    generated_text:   str        # 当前生成的原始正文（含标签）
    display_text:     str        # 去标签后的展示正文
    purity_result:    dict       # {passed, violations, stats}
    purity_retries:   int        # Purity Check 重试次数

    # ── STEP 4 结算 ──────────────────────────────────────────────────────────
    system_grants:    list[dict] # 从正文提取的 <system_grant> 标签列表
    narrative_seeds:  list[dict] # 从正文提取的 <narrative_seed> 标签列表
    calibration_result: dict     # Calibrator 数值校准结果
    growth_results:   list[dict] # XP 结算结果列表

    # ── 规划（Planner 输出）──────────────────────────────────────────────────
    planner_guidance:   dict         # 下一回合叙事建议
    hook_updates:       list[dict]   # 新增/更新的伏笔
    npc_drift_warnings: list[str]    # NPC 漂移警告（简短字符串列表）
    npc_drift_details:  list[dict]   # NPC 漂移详细报告（完整 JSON）
    word_count_range:   dict         # Planner 指定的正文字数建议 {"min": int, "max": int|None}

    # ── SSE 队列（各节点推送事件，端点消费）──────────────────────────────────
    sse_queue:     Optional[asyncio.Queue]  # asyncio.Queue[str]

    # ── 流程控制 ─────────────────────────────────────────────────────────────
    workflow_step: int           # 当前 WorkflowStep
    should_abort:  bool          # True = DM 拒绝，立即结束
    error_msg:     str           # 错误信息

    # ── 回滚语柄（STEP 4 归档前生成）────────────────────────────────────────
    rollback_snapshot: dict      # {chapter_id, protagonist_snapshot, message_order}


# ════════════════════════════════════════════════════════════════════════════
# 辅助函数
# ════════════════════════════════════════════════════════════════════════════

def push_sse(state: AgentState, event_type: SSEEventType, **payload) -> None:
    """非阻塞推送 SSE 事件到队列"""
    queue = state.get("sse_queue")
    if queue is None:
        return
    event = sse_event(event_type, **payload)
    try:
        queue.put_nowait(event)
    except asyncio.QueueFull:
        pass  # SSE 队列满时丢弃（不阻塞 Agent）


def push_log(state: AgentState, step: int, content: str) -> None:
    push_sse(state, SSEEventType.LOG, step=step, content=content)


def push_thought(state: AgentState, agent: str, content: str) -> None:
    push_sse(state, SSEEventType.THOUGHT, agent=agent, content=content)


def push_text(state: AgentState, text: str) -> None:
    push_sse(state, SSEEventType.NOVEL_TEXT, content=text)


def push_error(state: AgentState, content: str) -> None:
    push_sse(state, SSEEventType.ERROR, content=content)


def empty_state(
    novel_id: str,
    user_input: str,
    chapter_id: str = "",
    world_key: str = "",
    sse_queue: Optional[asyncio.Queue] = None,
) -> AgentState:
    """创建初始化状态"""
    return AgentState(
        novel_id=novel_id,
        world_key=world_key,
        chapter_id=chapter_id,
        user_input=user_input,
        stat_data={},
        owned_items=[],
        medals={},
        char_points=0,
        dm_verdict="",
        dm_feedback="",
        dm_modified_input="",
        scene_type="normal",
        world_context={},
        memory_context={"core": [], "recalled": []},
        active_npcs=[],
        npc_responses=[],
        sandbox_result={},
        style_stack=[],
        style_content="",
        generated_text="",
        display_text="",
        purity_result={},
        purity_retries=0,
        system_grants=[],
        narrative_seeds=[],
        calibration_result={},
        growth_results=[],
        planner_guidance={},
        hook_updates=[],
        npc_drift_warnings=[],
        npc_drift_details=[],
        word_count_range={},
        sse_queue=sse_queue,
        workflow_step=0,
        should_abort=False,
        error_msg="",
        rollback_snapshot={},
    )
