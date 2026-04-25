"""
Style Director Agent (Agent 4) — 文风栈选取
"""
from __future__ import annotations
import re
from pathlib import Path
from agents.state import AgentState, push_log, WorkflowStep

async def run_style_director(state: AgentState) -> AgentState:
    push_log(state, WorkflowStep.WRITING, "STEP 3a：文风选取…")

    from config import get_settings
    s = get_settings()
    styles_dir = s.writing_styles_dir

    scene_type = state.get("scene_type", "normal")
    try:
        import json as _json
        from db.queries import get_db
        novel_row = await get_db().get_novel(state["novel_id"])
        raw_stack = (novel_row.get("default_style_stack", []) or []) if novel_row else []
        # get_novel() 返回原始 DB 行，JSON 字段可能未反序列化，需手动解析
        if isinstance(raw_stack, str):
            try:
                raw_stack = _json.loads(raw_stack)
            except Exception:
                raw_stack = []
        default_stack = raw_stack if isinstance(raw_stack, list) else []
    except Exception:
        default_stack = []

    # 场景→文风映射
    scene_style_map = {
        "combat":     ["零度写作", "节奏大师", "行为细节派"],
        "normal":     ["零度写作", "物理细节派"],
        "dialogue":   ["零度写作", "对话节奏派"],
        "introspect": ["零度写作", "意识流轻化"],
    }
    selected = scene_style_map.get(scene_type, ["零度写作"])
    if default_stack:
        selected = list(dict.fromkeys(default_stack + selected))

    # 加载文风文件
    style_texts = []
    for style_name in selected[:3]:
        style_file = styles_dir / f"{style_name}.md"
        if style_file.exists():
            content = style_file.read_text(encoding="utf-8")
            style_texts.append(f"# {style_name}\n" + content[:2000])
        else:
            for f in styles_dir.glob("*.md"):
                if style_name.replace(" ", "") in f.stem.replace(" ", ""):
                    content = f.read_text(encoding="utf-8")
                    style_texts.append(f"# {style_name}\n" + content[:2000])
                    break

    state["style_stack"]   = selected
    state["style_content"] = "\n\n---\n\n".join(style_texts)
    push_log(state, WorkflowStep.WRITING, f"STEP 3a 完成：文风={selected}")
    return state


"""
NPC Actors Agent (Agent 3) — NPC 并发演绎
"""

NPC_SYSTEM_PROMPT = """
你正在扮演一个 NPC。严格遵守：
1. 只能知道你的 knowledge_scope 中包含的信息
2. 保持 trait_lock 中描述的性格特质不变
3. 你的行动不能超出你的 capability_cap（能力上限）
4. 用第一人称私下思考，输出行动计划（不直接输出对话文字）

输出格式（JSON）：
{
  "npc_name": "xxx",
  "thought": "内心想法（不超出知识边界）",
  "planned_action": "实际行动计划",
  "dialogue": "如果要说话，这里填对话内容（可以为空）",
  "emotion": "当前情绪状态"
}
"""

async def run_npc_actors(state: AgentState) -> AgentState:
    push_log(state, WorkflowStep.WORLD_CHECK, "STEP 2：NPC 演绎…")

    active_npcs = state.get("active_npcs", [])
    if not active_npcs:
        state["npc_responses"] = []
        return state

    from db.queries import get_db
    from utils.llm_client import get_llm_client
    import asyncio

    db  = get_db()
    llm = get_llm_client()
    novel_id  = state["novel_id"]
    user_input = state.get("user_input", "")
    stat_data  = state.get("stat_data", {})
    scene_desc = f"主角行动：{user_input}\n主角当前位置：{stat_data.get('world_key', '未知')}"

    async def simulate_npc(npc_name: str) -> dict:
        npc_data = await db.get_npc(novel_id, npc_name)
        if not npc_data:
            return {"npc_name": npc_name, "thought": "", "planned_action": "（无档案，保持被动）", "dialogue": ""}

        # NPC-1: psyche_model/capability_cap 可能是 JSON 字符串，需反序列化
        import json as _json
        def _safe_parse(val):
            if isinstance(val, str):
                try:
                    return _json.loads(val)
                except Exception:
                    return val
            return val or {}

        psyche_model   = _safe_parse(npc_data.get("psyche_model"))
        capability_cap = _safe_parse(npc_data.get("capability_cap"))
        trait_lock     = _safe_parse(npc_data.get("trait_lock")) or []
        knowledge_scope = _safe_parse(npc_data.get("knowledge_scope")) or []

        # NPC-2: Companion NPC 注入好感度和忠诚类型上下文
        companion_context = ""
        npc_type = npc_data.get("npc_type", "")
        if npc_type == "companion":
            affinity      = npc_data.get("initial_affinity", 50)
            loyalty_type  = npc_data.get("loyalty_type", "中性")
            companion_context = (
                f"\n[同伴关系] 好感度: {affinity}/100，忠诚类型: {loyalty_type}\n"
                f"提示：在该好感度/忠诚类型下，'{npc_name}' 对主角的配合度与信任程度应有对应体现。"
            )

        npc_prompt = f"""NPC 档案：
姓名：{npc_name}
性格特质（不可改变）：{trait_lock}
已知信息范围：{knowledge_scope}
能力上限：{capability_cap}
当前精神状态：{psyche_model}
{companion_context}
当前场景：
{scene_desc}

请以 {npc_name} 的视角，对场景做出反应。格式要求见 System Prompt。
"""

        try:
            result = await llm.chat_json(
                messages=[
                    {"role": "system", "content": NPC_SYSTEM_PROMPT},
                    {"role": "user",   "content": npc_prompt},
                ],
                role="npc_actors",
                temperature=0.7,
            )
            result["npc_name"] = npc_name
            return result
        except Exception as e:
            return {"npc_name": npc_name, "planned_action": "（演绎失败）", "dialogue": "", "error": str(e)}

    # 并发模拟所有 NPC
    tasks = [simulate_npc(name) for name in active_npcs[:5]]
    responses = await asyncio.gather(*tasks)

    state["npc_responses"] = list(responses)
    push_log(state, WorkflowStep.WORLD_CHECK, f"STEP 2 NPC 完成：{len(responses)} 个")
    return state
