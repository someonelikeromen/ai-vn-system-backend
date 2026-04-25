"""
Chronicler Agent (Agent 5) — STEP 3 正文生成 + Purity Check + STEP 4 归档
"""
from __future__ import annotations
from agents.state import AgentState, push_log, push_thought, push_text, WorkflowStep

CHRONICLER_SYSTEM_PROMPT_TEMPLATE = """
你是一位执行「零度叙事纪律」的专业小说书记员。

【文风规范】
{style_content}

【零度叙事铁律】
1. 禁止直接叙述内心状态，用行为/感知呈现
2. 禁止套话排比，每句话要推进信息
3. 正文每段不超过120字
4. 结合上下文保持时间线连续性
5. 如场景含战斗，必须用精确动作描写（不说"攻击"，说具体动作）

【世界技术铁律（绝对禁止违反）】
6. 只能使用当前世界设定中存在的技术/物品/概念
7. 严禁出现当前世界观之外的技术名词（如：现实世界科技、其他世界专属技术）
8. 如记忆召回内容中含有其他世界的技术概念，仅作情境参考，禁止直接复制到当前场景正文中
9. 当前世界的技术水平由【主角状态】中的世界设定决定——凡是与世界背景矛盾的内容，一律禁止出现

═══════════════════════════════════════════════════════
【熟练度等级写作规范（规格 §3.4，必须严格遵守）】

技能熟练度影响战斗描写方式，必须根据主角各技能的当前熟练度等级决定叙写风格：

| 熟练等级 | 战斗描写规范 | 效率系数 |
|---------|------------|--------|
| 入门    | 招式有明显延迟；动作不够流畅；偶有失手或走形；面对突发情况容易出错；奥义技完全不可用；是否能打出效果带有不确定性 | ×0.70 |
| 熟练    | 动作流畅自然，本能反应；基础招式无失误率；可稳定使用全套奥义；是能力的标准输出状态 | ×1.00 |
| 精通    | 招式可实时改造以适应对手；偶尔展示出「教科书之外」的变形运用；奥义在关键时刻自然爆发 | ×1.25 |
| 化境    | 可当场创造全新招式；旧招式在当前境界下产生质变效果；偶尔可以「教」NPC或对手 | ×1.60 |

⚠️ 写战斗时，必须查看【主角技能熟练度】部分，根据该技能的实际等级决定写法。
⚠️ 入门级技能在高压战斗中使用必须体现不稳定性和潜在失误风险。
⚠️ 奥义技的使用资格：入门=不可用；熟练=可稳定使用；精通/化境=使用时可产生变体效果。

【战斗输出参考公式（规格 §3.4）】
实际战斗输出 ≈ 能力星级基础威力 × 熟练度系数 × Hax适用性修正
示例：3★技能，熟练度=入门（×0.70）→ 实际输出约等于 2★~3★L 水平，且有失误风险

═══════════════════════════════════════════════════════
【数值标签规则】
在正文内嵌入数值结算标签（DM、书记员不得删除）：
- 击败敌人：<system_grant type="kill" tier="X" tier_sub="L/M/U" kill_type="defeat/kill"/>
- 经验值：<system_grant type="xp" school="技能名" amount="数值" context="vs_equal/vs_equal_win/vs_stronger/vs_stronger_win/vs_stronger_alive/vs_weaker/training"/>
  （context说明：vs_equal=同级参与，vs_equal_win=同级战胜，vs_stronger=强敌参与，
   vs_stronger_win=以弱胜强，vs_stronger_alive=存活且对手受创，vs_weaker=碾压弱敌，training=训练）
- 属性变化：<system_grant type="stat" attr="STR" delta="0.1"/>
- 能量消耗：<system_grant type="energy" pool="池名" delta="-20"/>
- 添加状态：<system_grant type="status_effect" action="add" name="燃血术" duration="3回合" effect="STR+50%"/>
- 移除状态：<system_grant type="status_effect" action="remove" name="燃血术"/>
- 积分（任务/成就）：<system_grant type="points" amount="100"/>
- 伏笔种子：<narrative_seed id="seed_xxx" text="简短伏笔描述" urgency="low/medium/high"/>

【输出格式】
直接输出正文（不要 markdown 代码块，不要解释），正文中可直接插入 XML 标签。
{word_count_directive}
"""

async def run_chronicler(state: AgentState) -> AgentState:
    push_log(state, WorkflowStep.WRITING, "STEP 3b：书记员创作中…")

    from utils.llm_client import get_llm_client
    from utils.tag_parser import extract_system_grants, extract_narrative_seeds, strip_grants_from_text
    from utils.purity_check import purity_check, DEFAULT_PURITY_CONFIG
    from config import get_settings

    llm  = get_llm_client()
    s    = get_settings()
    novel_id  = state["novel_id"]
    world_key = state.get("world_key", "")

    # 组装 Prompt
    user_input   = state.get("dm_modified_input") or state.get("user_input", "")
    stat_data    = state.get("stat_data", {})
    style_content = state.get("style_content", "（默认零度叙事风格）")
    memory_ctx   = state.get("memory_context", {"core": [], "recalled": []})
    npc_responses = state.get("npc_responses", [])
    sandbox_result = state.get("sandbox_result", {})
    scene_type   = state.get("scene_type", "normal")

    # 字数指令：由 Planner 动态指定，默认不设上限
    word_count_range = state.get("word_count_range", {})
    wc_min = word_count_range.get("min", 300)
    wc_max = word_count_range.get("max", None)
    if wc_max:
        word_count_directive = f"字数要求：{wc_min}～{wc_max}字（根据情节紧张度可适度调整）。"
    else:
        word_count_directive = f"字数要求：不少于 {wc_min} 字，无上限，根据情节需要自然收尾。"

    # 构建上下文摘要
    core_summary = "\n".join(
        f"[规则] {n.get('title','')}: {n.get('content','')[:100]}"
        for n in memory_ctx.get("core", [])[:4]
    )
    recalled_summary = "\n".join(
        f"[{r.get('metadata',{}).get('node_type','')}] "
        f"{r.get('metadata',{}).get('node_title','')}: {r.get('content','')[:80]}"
        for r in memory_ctx.get("recalled", [])[:6]
    )
    npc_context = "\n".join(
        f"{n.get('npc_name','')}: {n.get('planned_action','')} "
        f"| 将说：{n.get('dialogue','（沉默）')[:60]}"
        for n in npc_responses[:4]
    )
    sandbox_context = ""
    if sandbox_result.get("expected_consequences"):
        sandbox_context = f"沙盒推演结果: {sandbox_result['expected_consequences'][:200]}"
    if sandbox_result.get("combat_strategy"):
        sandbox_context += f"\n推荐应对策略: {sandbox_result['combat_strategy'][:200]}"
    if sandbox_result.get("energy_interaction"):
        sandbox_context += f"\n能量交互状态: {sandbox_result['energy_interaction'][:100]}"


    stat_summary = (
        f"主角：{stat_data.get('name','主角')} "
        f"| {stat_data.get('tier',0)}★{stat_data.get('tier_sub','M')} "
        f"| 积分：{stat_data.get('points',0)}"
    )

    status_effects = stat_data.get("status_effects", [])
    if status_effects:
        stat_summary += "\n[当前临时状态（Buff/Debuff）]：\n" + "\n".join(
            f"- {s.get('name')}: {s.get('effect')} (持续: {s.get('duration', '未知')})"
            for s in status_effects
        )

    # 构建技能熟练度摘要（注入战斗写作参考）
    from db.queries import get_db
    skill_proficiency_summary = ""
    try:
        db = get_db()
        owned_items = await db.get_owned_items(novel_id, "ApplicationTechnique")
        skill_lines = []
        for item in owned_items[:8]:  # 最多8个技能
            payload = item.get("payload", {})
            effects = payload.get("effects", {})
            for tech in effects.get("applicationTechniques", []):
                school = tech.get("schoolName", item.get("item_name", ""))
                prof   = tech.get("proficiencyLevel", "入门")
                tier   = item.get("final_tier", 0)
                sub    = item.get("final_sub", "M")
                skill_lines.append(f"- {school}（{tier}★{sub}）: 熟练度={prof}")
        if skill_lines:
            skill_proficiency_summary = "\n".join(skill_lines)
    except Exception:
        pass

    system_prompt = CHRONICLER_SYSTEM_PROMPT_TEMPLATE.format(
        style_content=style_content[:3000],
        word_count_directive=word_count_directive,
    )

    world_name = state.get("world_context", {}).get("world_name") or world_key or "主世界"

    user_prompt = f"""
<!-- scene: {scene_type} -->
<!-- style: {'+'.join(state.get('style_stack', ['零度写作']))} -->
<!-- world: {world_name}（严禁出现该世界观之外的技术/设定）-->

主角状态：{stat_summary}

主角技能熟练度（战斗写作必须参照）：
{skill_proficiency_summary or '（无技能档案，按默认处理）'}

世界规则参考：
{core_summary or '（暂无）'}

相关情境：
{recalled_summary or '（暂无）'}

NPC 行动计划：
{npc_context or '（当前场景无活跃NPC）'}

{sandbox_context}

用户行动：{user_input}

请以「零度叙事纪律」创作本回合的正文，含必要的 system_grant 标签。
当前世界为「{world_name}」，必须严格遵守该世界的技术水平和设定范围。
战斗场景中：必须根据上方技能熟练度等级，决定每项技能的描写风格（入门=延迟/不稳定，化境=流畅/可创造新招）。
"""

    # 重试循环（Purity Check 失败时重新生成）
    max_retries = s.purity_max_retries
    retries = state.get("purity_retries", 0)

    # max_tokens 按 Planner 指定上限自适应（上限字数 * 2.5 换算 token，至少 4096，最高 16384）
    wc_max_for_tokens = word_count_range.get("max", None)
    if wc_max_for_tokens:
        max_tokens = min(max(int(wc_max_for_tokens * 2.5), 4096), 16384)
    else:
        max_tokens = 8192  # 无上限时给足空间

    try:
        generated = await llm.chat(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_prompt},
            ],
            role="chronicler",
            temperature=0.85,
            max_tokens=max_tokens,
        )
    except Exception as e:
        push_thought(state, "chronicler", f"生成失败: {e}")
        state["should_abort"] = True
        state["error_msg"] = str(e)
        return state

    # Purity Check
    styles_dir = s.writing_styles_dir
    purity_result = purity_check(
        text=generated,
        config=DEFAULT_PURITY_CONFIG,
        styles_dir=styles_dir,
        scene_type=scene_type,
    )

    if not purity_result["passed"] and retries < max_retries:
        violations = purity_result["violations"]
        push_thought(state, "chronicler",
                     f"Purity Check 失败（第{retries+1}次），重试…\n违规: {violations}")
        state["purity_retries"] = retries + 1
        # 强制在 prompt 中加入违规说明重新生成
        user_prompt += f"\n\n【纯度检查失败，请修正以下问题后重新创作】：\n" + "\n".join(f"- {v}" for v in violations)
        try:
            generated = await llm.chat(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user",   "content": user_prompt},
                ],
                role="chronicler",
                temperature=0.75,
                max_tokens=max_tokens,
            )
            purity_result = purity_check(generated, DEFAULT_PURITY_CONFIG, styles_dir, scene_type)
        except Exception:
            pass

    # 流式推送正文（模拟打字机效果）
    display_text = strip_grants_from_text(generated)
    push_text(state, display_text)

    # 提取结构化标签
    grants  = extract_system_grants(generated)
    seeds   = extract_narrative_seeds(generated)

    push_thought(state, "chronicler",
                 f"Purity: {'✓' if purity_result['passed'] else '✗'} "
                 f"| grants={len(grants)} seeds={len(seeds)}")

    state["generated_text"]  = generated
    state["display_text"]    = display_text
    state["purity_result"]   = purity_result
    state["system_grants"]   = grants
    state["narrative_seeds"] = seeds
    state["workflow_step"]   = WorkflowStep.ARCHIVING

    push_log(state, WorkflowStep.WRITING,
             f"STEP 3b 完成：字数={len(display_text)}, "
             f"grants={len(grants)}, purity={'✓' if purity_result['passed'] else '✗'}")
    return state
