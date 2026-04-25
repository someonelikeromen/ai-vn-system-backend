"""
Calibrator Agent (Agent 7) — STEP 4 数值校准与XP结算
Sandbox Agent (Agent 6) — STEP 2 因果沙盒推演
Planner Agent (Agent 8) — STEP 4 规划 + NPC漂移检测
"""
from __future__ import annotations
from agents.state import AgentState, push_log, push_thought, WorkflowStep


# ════════════════════════════════════════════════════════════════════════════
# Sandbox Agent
# ════════════════════════════════════════════════════════════════════════════

SANDBOX_PROMPT = """
你是小说的因果推演引擎，同时兼任战务分析与沙盒裁判学。

═══════════════════════════════════════════════════════
【战力对比策略规则（规格 §4.1 Step 3）】
评估战斗时，必须依据以下规则判断可行策略：
• 主角 STR 或 DUR 高出对方 2★+ → 可不释招正面硬撼对方
• 主角 AGI 或 REF 高出对方 1★+ → 可利用速度差/预判差打空击
• 主角有 Hax 且 HI(有效跨级数) >= 星级差 → Hax 可有效命中（否则对方免疫）
• 主角 PER 高出对方 1★+ → 可利用感知差在对方行动前预判圆
• 虽大强对方不应徒劳无功战斗，但存在 Hax/速度/策略上优势时可安排应对方案

═══════════════════════════════════════════════════════
【跨宇宙能量体系交互规则（规格 §2.6）】
推演战斗时，判断主角持有的多系能量之间的交互状态：

| 状态     | 判定依据 | 推演影响 |
|---------|---------|--------|
| **同源相容** | 同一能量体系的不同应用 | 可同时激活，自然叠加，无额外消耗 |
| **异源相容** | 不同体系但原理不对立 | 可同时激活；「同类外放」（如两个生命力系体系）判相容；不同原理不冲突也相容；长期可探索协同（强协同×1.3效率） |
| **性质相斥** | 底层原理根本对立 | 同时激活：两者效率各降至60%，能量池各额外消耗15%；切换需要耗费1个行动时间 |
| **体系封锁** | 原作明确规定该体质无法使用该体系 | 该体系对主角完全无效，不可绕过（封锁仅限原作规则覆盖范围，跨宇宙体系不受影响） |

判定优先级：有明确「相斥/封锁」记录 → 按相斥/封锁处理；无明确记录，两者原理独立/同类外放 → 异源相容。

═══════════════════════════════════════════════════════
输出格式（JSON）：
{{
  "causal_chain": ["触发条件→直接结果→蝴蝶效应"],
  "expected_consequences": "综合描述（80字以内）",
  "combat_strategy": "战斗场景中的应对策略建议（如有）",
  "energy_interaction": "能量体系交互状态说明（如有多系能量）",
  "warnings": ["需要注意的叙事风险"],
  "suggested_scene_shift": "normal|combat|dialogue|escape（如场景类型应切换的话）"
}}
"""


async def run_sandbox(state: AgentState) -> AgentState:
    push_log(state, WorkflowStep.WORLD_CHECK, "STEP 2：沙盒推演…")

    scene_type = state.get("scene_type", "normal")
    # 非战斗场景快速跳过沙盒
    if scene_type not in ("combat", "dialogue"):
        state["sandbox_result"] = {"expected_consequences": "（普通场景，沙盒跳过）"}
        return state

    from utils.llm_client import get_llm_client
    llm = get_llm_client()

    user_input = state.get("dm_modified_input") or state.get("user_input", "")
    npc_plans  = [
        f"{n.get('npc_name','')}: {n.get('planned_action','')} | {n.get('emotion','')}"
        for n in state.get("npc_responses", [])
    ]
    stat_data  = state.get("stat_data", {})

    # 能量池摘要（用于沙盒判断相斥系统是否超出上限）
    energy_summary = ""
    try:
        energy_pools = stat_data.get("energy_pools", {}) or {}
        if isinstance(energy_pools, str):
            import json as _json
            energy_pools = _json.loads(energy_pools)
        ep_lines = [
            f"{name}: {v.get('current',0)}/{v.get('max',0)}"
            for name, v in energy_pools.items()
        ]
        energy_summary = " | ".join(ep_lines) if ep_lines else "无"
    except Exception:
        energy_summary = "无"

    prompt = f"""
场景类型：{scene_type}
主角行动：{user_input}
主角战力：{stat_data.get('tier',0)}★{stat_data.get('tier_sub','M')}
主角能量池余量：{energy_summary}
NPC 计划行动：
{chr(10).join(npc_plans) or '（无NPC）'}

请推演因果链。
"""

    try:
        result = await llm.chat_json(
            messages=[
                {"role": "system", "content": SANDBOX_PROMPT},
                {"role": "user",   "content": prompt},
            ],
            role="sandbox",
            temperature=0.4,
        )
    except Exception as e:
        result = {"expected_consequences": f"（推演失败: {e}）", "warnings": []}

    state["sandbox_result"] = result

    # 沙盒建议的场景切换
    if result.get("suggested_scene_shift") and result["suggested_scene_shift"] != "normal":
        state["scene_type"] = result["suggested_scene_shift"]

    push_log(state, WorkflowStep.WORLD_CHECK, "STEP 2 沙盒完成")
    return state


# ════════════════════════════════════════════════════════════════════════════
# Calibrator Agent
# ════════════════════════════════════════════════════════════════════════════

async def run_calibrator(state: AgentState) -> AgentState:
    push_log(state, WorkflowStep.ARCHIVING, "STEP 4：数值校准 + XP 结算…")

    from db.queries import get_db
    from exchange.pricing import calculate_combat_reward, TIER_BASE_PRICES
    from exchange.growth_service import growth_service
    from utils.tag_parser import classify_grants
    from utils.var_engine import VarEngine
    from config_sys.registry import AttributeSchemaRegistry

    db        = get_db()
    novel_id  = state["novel_id"]
    stat_data = state.get("stat_data", {})
    grants    = state.get("system_grants", [])

    if not grants:
        state["calibration_result"] = {"status": "no_grants"}
        return state

    classified = classify_grants(grants)

    # 初始化 VarEngine
    protagonist = await db.get_protagonist_state(novel_id)
    if protagonist:
        novel_row  = await db.get_novel(novel_id)
        schema_id  = novel_row.get("attr_schema_id", "standard_10d") if novel_row else "standard_10d"
        schema     = AttributeSchemaRegistry.get(schema_id)
        engine     = VarEngine(set(schema.get_keys()))
    else:
        engine = VarEngine.default()

    growth_results = []
    calibration_notes = []

    # 处理 kill 标签
    for kill in classified.get("kill", []):
        enemy_tier     = int(kill.get("tier", 0))
        enemy_tier_sub = kill.get("tier_sub", "M")
        kill_type      = kill.get("kill_type", "defeat")
        protagonist_tier = int(stat_data.get("tier", 0)) if stat_data else 0

        try:
            reward = await calculate_combat_reward(
                novel_id=novel_id,
                enemy_tier=enemy_tier,
                enemy_tier_sub=enemy_tier_sub,
                protagonist_tier=protagonist_tier,
                kill_type=kill_type,
            )
            # 自动加积分
            await db.add_points(novel_id, reward["points_earned"])
            if reward["medal_dropped"]:
                await db.add_medal(novel_id, enemy_tier)

            calibration_notes.append(
                f"击{'杀' if kill_type=='kill' else '败'} {enemy_tier}★{enemy_tier_sub}："
                f"+{reward['points_earned']}积分"
                + (f" +1枚{enemy_tier}★凭证" if reward["medal_dropped"] else "")
            )
        except Exception as e:
            calibration_notes.append(f"击杀结算失败: {e}")

    # 处理 points 标签
    for pt in classified.get("points", []):
        amount = int(pt.get("amount", 0))
        if amount != 0:
            await db.add_points(novel_id, amount)
            calibration_notes.append(f"积分变化: {amount:+}")

    # 处理 stat 标签（属性变化）
    for st in classified.get("stat", []):
        attr  = st.get("attr", "")
        delta = float(st.get("delta", 0))
        if attr and delta != 0 and protagonist:
            try:
                attrs = protagonist.get("attributes", {}) or {}
                attrs[attr] = round(attrs.get(attr, 1.0) + delta, 4)
                await db.update_protagonist_state(novel_id, attributes=attrs)
                calibration_notes.append(f"{attr}: {delta:+.2f}")
            except Exception as e:
                calibration_notes.append(f"属性更新失败: {e}")

    # 处理 energy 标签
    for en in classified.get("energy", []):
        pool  = en.get("pool", "")
        delta = int(en.get("delta", 0))
        if pool and delta != 0:
            await db.update_energy_pool(novel_id, pool, delta)

    # 处理 status_effect 标签 (临时状态增减)
    for eff in classified.get("status_effect", []):
        try:
            status_list = protagonist.get("status_effects", []) if protagonist else []
            name = eff.get("name", "")
            action = eff.get("action", "add")
            if not name: continue
            
            if action == "add":
                merged = False
                for existing in status_list:
                    if existing.get("name") == name:
                        existing["duration"] = eff.get("duration", existing.get("duration", ""))
                        if eff.get("effect"):
                            existing["effect"] = eff.get("effect")
                        merged = True
                        break
                if not merged:
                    status_list.append({
                        "name": name,
                        "duration": eff.get("duration", ""),
                        "effect": eff.get("effect", "")
                    })
                calibration_notes.append(f"附加状态：{name}")
                
            elif action == "remove":
                status_list = [s for s in status_list if s.get("name") != name]
                calibration_notes.append(f"解除状态：{name}")

            if protagonist:
                await db.update_protagonist_state(novel_id, status_effects=status_list)
                protagonist["status_effects"] = status_list
        except Exception as e:
            calibration_notes.append(f"状态更新失败: {e}")

    # 处理 xp 标签
    xp_grants_raw = classified.get("xp", [])
    if xp_grants_raw:
        owned_items = await db.get_owned_items(novel_id)
        enriched_xp = []
        for xp in xp_grants_raw:
            school = xp.get("school", "")
            matched_owned = None
            for oi in owned_items:
                payload = oi.get("payload", {})
                effects = payload.get("effects", {})
                for tech in effects.get("applicationTechniques", []):
                    if tech.get("schoolName", "") == school:
                        matched_owned = oi["id"]
                        break
                if matched_owned:
                    break
            if matched_owned:
                enriched_xp.append({**xp, "owned_id": matched_owned})

        if enriched_xp:
            import uuid
            event_id = str(uuid.uuid4())
            results = await growth_service.settle_xp_batch(
                novel_id=novel_id,
                chapter_id=state.get("chapter_id", ""),
                xp_grants=enriched_xp,
                event_id=event_id,
            )
            growth_results.extend(results)

    # ── 成就自动检测 ───────────────────────────────────────────────────────
    try:
        protagonist_now = await db.get_protagonist_state(novel_id)
        total_points = protagonist_now.get("points", 0) if protagonist_now else 0
        chapter_id_for_ach = state.get("chapter_id", "")

        # 首次击杀成就
        if classified.get("kill"):
            await db.unlock_achievement(
                novel_id=novel_id,
                achievement_key="first_kill",
                title="初战告捷",
                description="首次在战斗中击败或击杀敌人",
                chapter_id=chapter_id_for_ach,
            )

        # 高星级击杀成就
        for kill in classified.get("kill", []):
            etier = int(kill.get("tier", 0))
            if etier >= 5:
                await db.unlock_achievement(
                    novel_id=novel_id,
                    achievement_key=f"kill_tier_{etier}",
                    title=f"击败{etier}★强者",
                    description=f"击败/击杀了 {etier}★ 级别的强大对手",
                    chapter_id=chapter_id_for_ach,
                )

        # 积分里程碑成就
        for milestone, title, desc in [
            (1000,  "初入门道",  "累计积分达到 1,000"),
            (10000, "小有所成", "累计积分达到 10,000"),
            (50000, "大成境界", "累计积分达到 50,000"),
        ]:
            if total_points >= milestone:
                await db.unlock_achievement(
                    novel_id=novel_id,
                    achievement_key=f"points_{milestone}",
                    title=title,
                    description=desc,
                    chapter_id=chapter_id_for_ach,
                )
    except Exception:
        pass  # 成就失败不阻断主流程

    state["calibration_result"] = {
        "status": "done",
        "notes": calibration_notes,
        "growth_count": len(growth_results),
    }
    state["growth_results"] = growth_results

    push_log(state, WorkflowStep.ARCHIVING, f"STEP 4 校准完成: {calibration_notes}")
    return state


# ════════════════════════════════════════════════════════════════════════════
# Planner Agent
# ════════════════════════════════════════════════════════════════════════════

PLANNER_SYSTEM_PROMPT = """
你是小说规划师。分析本回合发展，提供下一回合的叙事建议。

输出格式（JSON）：
{{
  "arc_progress": "当前弧线进度评估（50字以内）",
  "next_turn_hint": "下回合叙事建议，包含伏笔激活建议（100字以内）",
  "hooks_to_activate": ["伏笔ID"],
  "hooks_to_register": [{{"description": "新伏笔", "urgency": "low/medium/high"}}],
  "npc_drift_warnings": ["NPC名: 漂移描述（严重漂移时给出修正方向）"],
  "word_count_min": 300,
  "word_count_max": null,
  "thought": "规划思路"
}}

字数建议原则：
- 战斗高潮、重要转折点：word_count_min=500，word_count_max=1200
- 普通行动、对话场景：word_count_min=300，word_count_max=可不设（null）
- 过渡小值、内心无岁：word_count_min=200，word_count_max=500
- 如不确定，设 word_count_min=300, word_count_max=null（不限制上限）
"""

NPC_DRIFT_SYSTEM_PROMPT = """
你是 NPC 人格一致性裁判官。判断一个 NPC 的本回合行为是否与其「稳定特质（trait_lock）」存在漂移。

判断标准：
- 「稳定特质」是 NPC 的核心不可变元素，类似设定中的性格检验
- 裁判漂移的程度：
  * 严重漂移：行为与特质正相反（如「严肃冷静」却突然「歇斯底里」）
  * 轻度漂移：行为偏出特质范围但尚可解释（如特定巨大压力下的局部应激）
  * 无漂移：行为完全符合特质，容许明确情境引发的短期情绪波动

输出格式（JSON）：
{{
  "npc_name": "xxx",
  "drift_level": "none | minor | severe",
  "drift_reason": "说明（无漂移时可为空字符串）",
  "offending_behavior": "具体矛盾的行为或对话片段（无则为空）",
  "offending_traits": ["被违反的特质描述"]
}}
"""


async def run_planner(state: AgentState) -> AgentState:
    push_log(state, WorkflowStep.ARCHIVING, "STEP 4：规划 + NPC漂移检测…")

    from utils.llm_client import get_llm_client
    from db.queries import get_db
    import asyncio

    llm = get_llm_client()
    db  = get_db()
    novel_id = state["novel_id"]

    generated       = state.get("display_text", "")
    user_input      = state.get("user_input", "")
    npc_responses   = state.get("npc_responses", [])
    narrative_seeds = state.get("narrative_seeds", [])
    sandbox_result  = state.get("sandbox_result", {})

    # ── NPC 漂移检测（LLM 判断，并发执行）────────────────────────────────────
    async def check_npc_drift(npc_resp: dict) -> dict | None:
        """对单个 NPC 做 trait_lock vs 本回合行为的 LLM 一致性裁判"""
        npc_name = npc_resp.get("npc_name", "")
        if not npc_name:
            return None

        npc_data = await db.get_npc(novel_id, npc_name)
        if not npc_data:
            return None

        trait_lock = npc_data.get("trait_lock", [])
        if isinstance(trait_lock, str):
            import json as _json
            try:
                trait_lock = _json.loads(trait_lock)
            except Exception:
                trait_lock = [trait_lock] if trait_lock else []

        if not trait_lock:
            return None  # 无稳定特质则跳过

        action   = npc_resp.get("planned_action", "")
        dialogue = npc_resp.get("dialogue", "")
        emotion  = npc_resp.get("emotion", "")

        if len(action + dialogue) < 8:
            return None  # 行为太少，无法有效判断

        drift_user_prompt = f"""NPC 档案：
姓名：{npc_name}
稳定特质（trait_lock，核心不可变）：
{chr(10).join(f'- {t}' for t in trait_lock)}

本回合行为记录：
行动计划：{action}
对话内容：{dialogue or '（无对话）'}
情绪状态：{emotion or '（未知）'}

本回合场景背景（节选）：
{generated[:300] or '（无正文）'}

请判断该 NPC 的本回合行为是否与其稳定特质存在漂移，并输出 JSON。"""

        try:
            drift_result = await llm.chat_json(
                messages=[
                    {"role": "system", "content": NPC_DRIFT_SYSTEM_PROMPT},
                    {"role": "user",   "content": drift_user_prompt},
                ],
                role="planner",
                temperature=0.2,
            )
            drift_result["npc_name"] = npc_name
            return drift_result
        except Exception:
            return None

    # 并发检测所有活跃 NPC（最多 5 个）
    drift_tasks   = [check_npc_drift(resp) for resp in npc_responses[:5]]
    drift_results = await asyncio.gather(*drift_tasks)

    # 提取漂移警告
    drift_warnings: list[str] = []
    for dr in drift_results:
        if not dr:
            continue
        level = dr.get("drift_level", "none")
        if level in ("minor", "severe"):
            reason  = dr.get("drift_reason", "")
            warning = f"{dr['npc_name']}: [{level.upper()}] {reason}"
            drift_warnings.append(warning)
            if level == "severe":
                push_log(state, WorkflowStep.ARCHIVING,
                         f"⚠️ NPC严重漂移: {dr['npc_name']} — {reason}")

    # ── Planner 主提示（注入沙盒结果 + drift 摘要）────────────────────────────
    sandbox_summary = ""
    if sandbox_result:
        sandbox_summary = (
            f"沙盒推演结论：{sandbox_result.get('expected_consequences', '')}\n"
            f"策略建议：{sandbox_result.get('combat_strategy', '')}\n"
            f"推演警示：{'; '.join(sandbox_result.get('warnings', []))}"
        ).strip()

    drift_summary = ""
    if drift_warnings:
        drift_summary = "⚠️ 本回合NPC漂移检测结果：\n" + "\n".join(
            f"  - {w}" for w in drift_warnings
        )

    prompt = f"""本回合情况：
用户行动：{user_input}
本回合正文（节选）：{generated[:500]}
活跃NPC：{[n.get('npc_name', '') for n in npc_responses]}
新诞生伏笔：{[s.get('text', '') for s in narrative_seeds]}

{sandbox_summary}

{drift_summary}

请基于以上信息，提供下一回合规划建议。如存在严重NPC漂移，请在 npc_drift_warnings 字段给出修正方向。
"""

    try:
        result = await llm.chat_json(
            messages=[
                {"role": "system", "content": PLANNER_SYSTEM_PROMPT},
                {"role": "user",   "content": prompt},
            ],
            role="planner",
            temperature=0.4,
        )
    except Exception as e:
        result = {"next_turn_hint": "", "npc_drift_warnings": [], "hooks_to_register": []}

    # 注册新伏笔
    hooks_to_register = result.get("hooks_to_register", [])
    for hook_def in hooks_to_register[:3]:
        desc    = hook_def.get("description", "")
        urgency = hook_def.get("urgency", "low")
        if desc:
            await db.register_hook(
                novel_id=novel_id,
                description=desc,
                seeded_at_chapter=state.get("chapter_id", ""),
                urgency=urgency,
            )

    # 合并独立 drift 检测 + Planner 主输出的漂移警告
    planner_drift = result.get("npc_drift_warnings", [])
    all_drift_warnings = drift_warnings + [
        w for w in planner_drift if w not in drift_warnings
    ]

    state["planner_guidance"]   = result
    state["hook_updates"]       = hooks_to_register
    state["npc_drift_warnings"] = all_drift_warnings
    state["npc_drift_details"]  = [dr for dr in drift_results if dr]

    # 将 Planner 建议的字数区间写入 state，下一回合 Chronicler 读取
    wc_min = result.get("word_count_min", 300)
    wc_max = result.get("word_count_max", None)
    if wc_min is not None:
        state["word_count_range"] = {"min": int(wc_min), "max": int(wc_max) if wc_max else None}

    push_log(state, WorkflowStep.ARCHIVING,
             f"STEP 4 规划完成（漂移检测: {len(drift_warnings)} 项警告）")
    return state

async def run_archiver(state: AgentState) -> AgentState:
    push_log(state, WorkflowStep.ARCHIVING, "STEP 4：归档…")

    from db.queries import get_db
    from memory.engine import memory_engine

    db = get_db()
    novel_id   = state["novel_id"]
    chapter_id = state.get("chapter_id", "")

    # ── 保存回合快照（在写消息前，记录本轮开始时的完整状态）──
    try:
        protagonist_before = await db.get_protagonist_state(novel_id)
        grants_this_turn   = state.get("system_grants", [])
        if protagonist_before:
            # 获取当前凭证状态
            medals_rows  = await db._fetchall(
                "SELECT stars, count FROM medals WHERE novel_id=?", (novel_id,)
            )
            # 获取当前成长记录（XP/等级）
            growth_rows  = await db._fetchall(
                "SELECT owned_id, growth_key, sub_key, current_xp, level_index, use_count, version "
                "FROM growth_records WHERE novel_id=?",
                (novel_id,),
            )
            await db.save_turn_snapshot(
                novel_id=novel_id,
                protagonist_before=protagonist_before,
                grants=grants_this_turn,
                medals=[dict(m) for m in medals_rows],
                growth_records=[dict(g) for g in growth_rows],
            )
    except Exception as _snap_err:
        pass  # 快照失败不阻断主流程

    # 保存用户消息
    await db.append_message(
        novel_id=novel_id,
        role="user",
        raw_content=state.get("user_input", ""),
        chapter_id=chapter_id,
    )

    # 保存 AI 响应（带标签的原始 + 去标签的展示）
    await db.append_message(
        novel_id=novel_id,
        role="assistant",
        raw_content=state.get("generated_text", ""),
        display_content=state.get("display_text", ""),
        chapter_id=chapter_id,
    )

    # 将伏笔种子写入 narrative_hooks
    for seed in state.get("narrative_seeds", []):
        desc = seed.get("text", "")
        if desc:
            await db.register_hook(
                novel_id=novel_id,
                description=desc,
                seeded_at_chapter=chapter_id,
                urgency=seed.get("urgency", "low"),
            )

    # 将记忆提取任务入队（非阻塞后台执行）
    messages = [
        {"role": "user",      "display_content": state.get("user_input", "")},
        {"role": "assistant", "display_content": state.get("display_text", "")},
    ]
    memory_engine.enqueue_extraction(
        novel_id=novel_id,
        world_key=state.get("world_key", ""),
        chapter_id=chapter_id,
        messages=messages,
    )

    push_log(state, WorkflowStep.ARCHIVING, "STEP 4 归档完成 ✓")
    return state
