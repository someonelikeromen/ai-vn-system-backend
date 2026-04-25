"""
DM Agent (Agent 2) — STEP 0 状态读取 + STEP 1 一致性验证
"""
from __future__ import annotations
from agents.state import AgentState, push_log, push_thought, push_error, WorkflowStep

DM_SYSTEM_PROMPT = """
你是这部小说世界的世界主（DM/GM）。
你需要严格执行主角行为的合理性验证，保护世界观的自洽性。

职责：
1. 验证主角行动在当前状态下是否物理可行（属性上限/技能前提/能量池余量）
2. 检查世界规则（属性上限/技能前提/世界锁定等）
3. 如行动不合理，给出修正建议（不要代替用户做决定）
4. 严禁开启“裁判视角”——不要混入NPC的主观认知

═══════════════════════════════════════════════════════
【兑换系统规则摘要（规格 §2.1-B）】
当主角表达要兑换分析时：
• 战斗外：无限制，随时兑换，即时生效，无额外代价
• 战斗中：允许，但消耗当前回合主动权，当回合对手获得一次不受干扰的自由行动
• 濒死状态兑换：允许，系统优先级最高，但兑换能力的初始熟练度额外-10%（紧急强度惩罚）
验证兑换类行动时，检查：积分是否充足，否则 reject；战斗中兑换必须提醒会失去当回合。

═══════════════════════════════════════════════════════
【场景类型判定细则】
• combat：存在敌对实体且响应战斗技能，或主角明确表达战斗意图
• dialogue：主要交流场景，NPC有情绪反应需求但未直接展开战斗
• introspect：主角内心独白/深度思考，无外部互动主导
• normal：其他所有场景

═══════════════════════════════════════════════════════
输出格式（JSON）：
{
  "verdict": "pass | reject | modify",
  "feedback": "说明（通过时简短，拒绝/修正时详细）",
  "modified_input": "修正后的行动文字（仅 modify 时）",
  "scene_type": "normal | combat | dialogue | introspect",
  "active_npcs": ["李四", "张三"],
  "thought": "DM内部推理过程"
}
"""

async def run_dm(state: AgentState) -> AgentState:
    push_log(state, WorkflowStep.STATE_READ, "STEP 0：读取状态与记忆召回…")

    from db.queries import get_db
    from memory.engine import memory_engine
    from utils.llm_client import get_llm_client
    from utils.locks import NovelStateRefreshBus

    novel_id  = state["novel_id"]
    world_key = state.get("world_key", "")
    db = get_db()
    llm = get_llm_client()

    # ── STEP 0A: 检查状态脏位强制重载 ──────────────────────────────────
    if NovelStateRefreshBus.is_dirty(novel_id):
        stat_data = await db.get_protagonist_state(novel_id) or {}
        NovelStateRefreshBus.consume(novel_id)
    else:
        stat_data = await db.get_protagonist_state(novel_id) or {}

    owned_items = await db.get_owned_items(novel_id)
    medals_rows = await db._fetchall(
        "SELECT stars, count FROM medals WHERE novel_id=?", (novel_id,)
    )
    medals = {int(r["stars"]): int(r["count"]) for r in medals_rows}  # key 必须为 int
    active_hooks = await db.get_active_hooks(novel_id)

    # 读取世界档案（锁定状态/时间流速/峰值战力）
    world_context = {}
    try:
        world_row = await db._fetchone(
            "SELECT time_flow_ratio, time_flow_type, peak_tier, peak_tier_sub, "
            "world_name, entered_at "
            "FROM world_archives WHERE novel_id=? AND world_key=?",
            (novel_id, world_key)
        ) if world_key else None
        if world_row:
            world_context = dict(world_row)
        # 主角锁定状态
        locked_until = stat_data.get("world_locked_until") if stat_data else None
        if locked_until:
            world_context["world_locked_until"] = locked_until
    except Exception:
        pass
    recent_msgs  = await db.get_messages(novel_id, limit=20)

    # ── STEP 0B: 四层记忆召回 ────────────────────────────────────────────
    push_log(state, WorkflowStep.STATE_READ, "STEP 0：四层记忆召回中…")
    user_input = state.get("user_input", "")
    protagonist_loc = stat_data.get("world_key", world_key) if stat_data else world_key

    memory_ctx = await memory_engine.recall(
        novel_id=novel_id,
        world_key=world_key,
        query_text=user_input,
        protagonist_location=protagonist_loc,
        viewer_agent="dm",
        top_k=15,
    )

    # ── STEP 1: 一致性验证 ────────────────────────────────────────────────
    push_log(state, WorkflowStep.CONSISTENCY, "STEP 1：DM 一致性验证…")

    recent_history = "\n".join(
        f"[{m['role']}] {(m.get('display_content') or m.get('raw_content',''))[:200]}"
        for m in reversed(recent_msgs[:10])
    )
    core_rules = "\n".join(
        f"- {n.get('title','')}: {n.get('content','')[:150]}"
        for n in memory_ctx.get("core", [])[:5]
    )
    recalled_context = "\n".join(
        f"- [{r.get('metadata',{}).get('node_type','')}] "
        f"{r.get('metadata',{}).get('node_title','')}: {r.get('content','')[:100]}"
        for r in memory_ctx.get("recalled", [])[:8]
    )

    stat_summary = {
        "name":    stat_data.get("name", "主角") if stat_data else "主角",
        "points":  stat_data.get("points", 0) if stat_data else 0,
        "tier":    stat_data.get("tier", 0) if stat_data else 0,
        "tier_sub":stat_data.get("tier_sub","M") if stat_data else "M",
        "attributes": stat_data.get("attributes", {}) if stat_data else {},
        "status_effects": stat_data.get("status_effects", []) if stat_data else [],
    }

    active_hooks_summary = "\n".join(
        f"- [{h['urgency']}] {h['description'][:100]}"
        for h in active_hooks[:5]
    )

    # 构建技能+能量池摘要
    skills_summary = ""
    energy_summary = ""
    try:
        owned_techniques = [item for item in owned_items if item.get("item_type") == "ApplicationTechnique"]
        skill_lines = []
        for item in owned_techniques[:6]:
            payload = item.get("payload", {})
            effects = payload.get("effects", {})
            for tech in effects.get("applicationTechniques", []):
                school = tech.get("schoolName", item.get("item_name", ""))
                prof   = tech.get("proficiencyLevel", "入门")
                tier   = item.get("final_tier", 0)
                skill_lines.append(f"- {school}（{tier}★）熟练度={prof}")
        if skill_lines:
            skills_summary = "\n".join(skill_lines)
    except Exception:
        pass

    try:
        energy_pools = stat_data.get("energy_pools", {}) or {}
        if isinstance(energy_pools, str):
            import json as _json_import
            energy_pools = _json_import.loads(energy_pools)
        ep_lines = [
            f"- {name}: {v.get('current',0)}/{v.get('max',0)}"
            for name, v in energy_pools.items()
        ]
        energy_summary = "\n".join(ep_lines) if ep_lines else "无能量池"
    except Exception:
        energy_summary = "无能量池"

    # 构建世界锁定说明
    world_lock_notice = ""
    wc_locked = world_context.get("world_locked_until")
    if wc_locked:
        world_lock_notice = f"\n⚠️ 世界穿越锁定：主角当前在目标世界，需在目标世界时间 {wc_locked} 后方可穿越离开。"
    wc_peak = world_context.get("peak_tier")
    if wc_peak:
        world_lock_notice += f"\n当前世界峰值战力：{wc_peak}★{world_context.get('peak_tier_sub','M')}，时间流速比：{world_context.get('time_flow_ratio','1:1')}"

    dm_prompt = f"""
当前状态：
主角：{stat_summary}
当前世界：{world_key or '（默认）'}{world_lock_notice}

主角当前技能与熟练度：
{skills_summary or '（暂无技能档案）'}

主角能量池余量：
{energy_summary}

近期对话（最近10轮）：
{recent_history}

世界规则（Core层）：
{core_rules or '（暂无记录）'}

相关情境（召回层）：
{recalled_context or '（暂无）'}

活跃伏笔/任务：
{active_hooks_summary or '（无）'}

用户行动：{user_input}

请验证此行动的合理性并输出 JSON。
注意：如行动涉及兑换，检查积分是否充足；如在战斗中兑换，提醒主角将失去当回合主动权且对手获得自由行动机会；如存在世界锁定且行动意图离开当前世界，则 reject。
"""

    try:
        result = await llm.chat_json(
            messages=[
                {"role": "system", "content": DM_SYSTEM_PROMPT},
                {"role": "user",   "content": dm_prompt},
            ],
            role="dm",
            temperature=0.3,
        )
    except Exception as e:
        push_error(state, f"DM 验证失败: {e}")
        state["should_abort"] = True
        state["error_msg"] = str(e)
        return state

    verdict   = result.get("verdict", "pass")
    feedback  = result.get("feedback", "")
    thought   = result.get("thought", "")
    scene_type = result.get("scene_type", "normal")
    active_npcs = result.get("active_npcs", [])

    push_thought(state, "dm", thought or feedback)

    if verdict == "reject":
        push_error(state, f"[DM] 行动不合理：{feedback}")
        state["should_abort"] = True
        state["dm_verdict"]   = "reject"
        state["dm_feedback"]  = feedback
    elif verdict == "modify":
        modified = result.get("modified_input", user_input)
        push_thought(state, "dm", f"行动已修正为：{modified}")
        state["dm_verdict"]        = "modify"
        state["dm_feedback"]       = feedback
        state["dm_modified_input"] = modified
    else:
        state["dm_verdict"]  = "pass"
        state["dm_feedback"] = feedback

    state["stat_data"]       = stat_data or {}
    state["owned_items"]     = owned_items
    state["medals"]          = medals
    state["char_points"]     = (stat_data.get("points", 0) if stat_data else 0)
    state["memory_context"]  = memory_ctx
    state["world_context"]   = world_context   # DM-2: 写入世界档案
    state["scene_type"]      = scene_type
    state["active_npcs"]     = active_npcs
    state["workflow_step"]   = WorkflowStep.WORLD_CHECK

    push_log(state, WorkflowStep.CONSISTENCY,
             f"STEP 1 完成：verdict={verdict}, scene={scene_type}")
    return state
