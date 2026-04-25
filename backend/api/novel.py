"""
API — 小说管理路由
POST   /api/novels/           创建新小说
GET    /api/novels/           列表
GET    /api/novels/{id}       详情
PATCH  /api/novels/{id}       更新
DELETE /api/novels/{id}       删除
POST   /api/novels/{id}/init  初始化主角
"""
from __future__ import annotations

import json as _json
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from db.queries import get_db, Database
from config_sys.registry import AttributeSchemaRegistry

router = APIRouter(prefix="/api/novels", tags=["novels"])


def _db() -> Database:
    return get_db()


# ── 请求/响应模型 ──────────────────────────────────────────────────────────

class CreateNovelRequest(BaseModel):
    title: str
    ip_type: str = "original"
    world_type: str = "single_world"
    current_world_key: str = ""
    attr_schema_id: str = "standard_10d"


class UpdateNovelRequest(BaseModel):
    title: Optional[str] = None
    current_world_key: Optional[str] = None
    default_style_stack: Optional[list] = None
    archived: Optional[bool] = None
    ip_type: Optional[str] = None


class InitProtagonistRequest(BaseModel):
    name: str
    world_key: str = ""
    starting_points: int = 0
    initial_energy_pools: dict = {}


# ── 路由实现 ───────────────────────────────────────────────────────────────

@router.post("/", status_code=201)
async def create_novel(req: CreateNovelRequest, db: Database = Depends(_db)):
    """创建新小说项目"""
    # 验证 attr_schema_id 合法性
    schema = AttributeSchemaRegistry.get(req.attr_schema_id)
    novel_id = await db.create_novel(
        title=req.title,
        ip_type=req.ip_type,
        world_type=req.world_type,
        current_world_key=req.current_world_key,
        attr_schema_id=schema.schema_id,
    )
    novel = await db.get_novel(novel_id)
    return {"novel": novel, "message": "小说项目创建成功"}


@router.get("/")
async def list_novels(archived: bool = False, db: Database = Depends(_db)):
    """获取小说列表"""
    novels = await db.list_novels(archived=archived)
    return {"novels": novels, "count": len(novels)}


@router.get("/{novel_id}")
async def get_novel(novel_id: str, db: Database = Depends(_db)):
    """获取小说详情（含主角状态概览）"""
    novel = await db.get_novel(novel_id)
    if not novel:
        raise HTTPException(status_code=404, detail="小说不存在")
    protagonist = await db.get_protagonist_state(novel_id)
    chapters = await db.list_chapters(novel_id)
    active_hooks = await db.get_active_hooks(novel_id)
    return {
        "novel": novel,
        "protagonist": protagonist,
        "chapter_count": len(chapters),
        "active_hooks_count": len(active_hooks),
    }


@router.patch("/{novel_id}")
async def update_novel(
    novel_id: str, req: UpdateNovelRequest, db: Database = Depends(_db)
):
    """更新小说配置"""
    novel = await db.get_novel(novel_id)
    if not novel:
        raise HTTPException(status_code=404, detail="小说不存在")
    update_data = req.model_dump(exclude_none=True)
    if update_data:
        await db.update_novel(novel_id, **update_data)
    return {"message": "更新成功", "novel_id": novel_id}


@router.delete("/{novel_id}")
async def delete_novel(novel_id: str, db: Database = Depends(_db)):
    """删除小说（级联删除所有数据）"""
    novel = await db.get_novel(novel_id)
    if not novel:
        raise HTTPException(status_code=404, detail="小说不存在")
    await db.delete_novel(novel_id)
    return {"message": "删除成功", "novel_id": novel_id}


@router.post("/{novel_id}/init")
async def init_protagonist(
    novel_id: str, req: InitProtagonistRequest, db: Database = Depends(_db)
):
    """初始化主角（建档第1步）"""
    novel = await db.get_novel(novel_id)
    if not novel:
        raise HTTPException(status_code=404, detail="小说不存在")

    await db.init_protagonist(
        novel_id=novel_id,
        name=req.name,
        world_key=req.world_key,
        attr_schema_id=novel.get("attr_schema_id", "standard_10d"),
    )

    if req.starting_points > 0:
        await db.add_points(novel_id, req.starting_points)

    if req.initial_energy_pools:
        for pool_name, pool_data in req.initial_energy_pools.items():
            pool_data["name"] = pool_name
            await db.register_energy_pool(novel_id, pool_data)

    protagonist = await db.get_protagonist_state(novel_id)
    return {"message": "主角初始化成功", "protagonist": protagonist}


@router.get("/{novel_id}/protagonist")
async def get_protagonist(novel_id: str, db: Database = Depends(_db)):
    """获取完整主角状态（含技能/成长列表）"""
    protagonist = await db.get_protagonist_state(novel_id)
    if not protagonist:
        raise HTTPException(status_code=404, detail="主角未初始化")

    owned_items = await db.get_owned_items(novel_id)
    medals_rows = await db._fetchall(
        "SELECT stars, count FROM medals WHERE novel_id=?", (novel_id,)
    )
    medals = {int(r["stars"]): int(r["count"]) for r in medals_rows}

    return {
        "protagonist": protagonist,
        "owned_items": owned_items,
        "medals": medals,
    }


# ─── 主角 AI 生成 ─────────────────────────────────────────────────────────────

# 反理性化指令（移植自 tmp_ai_vn_game_system/characterPrompt.js）
_ANTI_RATIONAL = """
==== 【反理性化铁律 — 必须遵守】 ====

你正在创作一个真实的人，不是机器人，不是故事里的主角，不是道德楷模。

禁止项（出现则为失败）：
✗ 禁止"冷静分析局势"式的人格描述
✗ 禁止"缺陷是暗地里的优点"（如"看起来冷漠其实很温柔"——这不叫缺陷）
✗ 禁止用战略思维描述普通情绪
✗ 禁止天赋异禀、命中注定的设定（除非输入中明确有）
✗ 禁止把创伤处理成"使他变得更强"
✗ 禁止用形容词堆砌性格
✗ 禁止性格描述中全是优点，缺陷只有"有时候太努力"

必须包含的内容：
✓ 有血有肉的真实人，不是完美主角
✓ 日常行为而非英雄行为（他早上不想起床、他有时候因为小事烦躁一整天）
✓ 性格由具体的经历塑造，不是抽象的"天性"

【忠实原则】：
- 输入中已有的性格/缺点/渴望/恐惧描述，直接采用并具体化，不要重新发明
- 不要强行套用"必须有X类型缺陷/Y类型恐惧"的模板
"""

_TIER_REF = """
==== 【★星级参考 — 角色创建开局规则】 ====
- 普通人类出发：tier = 0（所有超凡体系开局也是0★）
- 有血脉觉醒/特殊天赋：被动能力 tier = 1（有但弱小）
- 禁止开局给高星级（3★以上等于已经是超级英雄）

attributes（10个属性）精确到0.1，范围0.5-1.8，基准1.0 = 健康成年人平均水平
"""

_CHAR_GEN_SYSTEM = """你是一位专业的角色创作者，专门创作真实、立体、有人味的RPG角色。

{anti_rational}

{tier_ref}

==== 【输出格式】 ====
用```json包裹，输出以下完整字段（省略任何字段将导致失败）：

```json
{{
  "name": "角色姓名",
  "gender": "男/女",
  "age": "25",
  "identity": "具体职业/社会身份（具体，如'县城代课老师'而非'老师'）",
  "height": "172cm",
  "weight": "60kg",
  "alignment": "混乱·中立",
  "appearance": "100字写实外貌：发色瞳色肤色体型气质，第一印象",
  "clothing": "50字以内惯常着装",
  "traits": ["核心标签1", "核心标签2", "核心标签3"],
  "personality": ["具体性格侧面描述"],
  "flaws": ["真实存在的缺点，不要美化"],
  "desires": ["根据角色实际情况"],
  "fears": ["根据角色实际情况"],
  "background": "120字背景故事：1-2个真实塑造性格的经历",
  "quirks": ["可观察的具体行为习惯"],
  "attributes": {{
    "STR": 1.0, "DUR": 1.0, "VIT": 1.0, "REC": 1.0, "AGI": 1.0,
    "REF": 1.0, "PER": 1.0, "MEN": 1.0, "SOL": 1.0, "CHA": 1.0
  }},
  "psyche_model": {{
    "dimensions": {{
      "social":    {{"introExtro": 0, "trustRadius": 0, "dominance": 0, "empathy": 0, "boundaryStrength": 0}},
      "emotional": {{"stability": 0, "expressiveness": 0, "recoverySpeed": 0, "emotionalDepth": 0}},
      "cognitive": {{"analyticIntuitive": 0, "openness": 0, "riskTolerance": 0, "selfAwareness": 0}},
      "values":    {{"autonomy": 0, "altruism": 0, "rationality": 0, "loyalty": 0, "idealism": 0}}
    }},
    "triggerPatterns": [
      {{"trigger": "具体触发情境", "reaction": "具体行为/情绪反应", "intensity": 7}}
    ]
  }},
  "knowledge": [
    {{"topic": "知识领域名", "type": "Theory", "mastery": "熟练", "summary": "50字简述"}}
  ],
  "passiveAbilities": [
    {{"name": "能力名", "tier": 1, "desc": "50字描述"}}
  ],
  "powerSources": [
    {{"poolName": "魔力/内力", "poolMax": 100, "poolRegen": "随时间恢复", "tier": 0, "desc": "运作原理及来源"}}
  ],
  "techniques": [
    {{"name": "技巧/招式名", "tier": 0, "desc": "50字描述"}}
  ],
  "startingItems": [
    {{"name": "随身物品名", "qty": 1, "type": "Tool", "desc": "50字描述"}}
  ],
  "relationships": [
    {{
      "name": "NPC姓名（背景中明确提及的相关人物）",
      "relation": "关系描述（如：义妹、青梅竹马、死对头、恩人）",
      "emotion_type": "family|romance|friendship|hostile|affiliated|mixed",
      "emotion_tags": ["亲情", "依赖"],
      "affinity": 80,
      "loyalty_type": "血缘亲情/利益绑定/情感联结/信仰共鸣",
      "trait_lock": ["稳定特质1", "稳定特质2"],
      "knowledge_scope": ["该NPC了解主角的信息"],
      "npc_type": "companion|antagonist|neutral",
      "background": "60字以内NPC自身背景",
      "appearance": "外貌简述（30字以内）"
    }}
  ]
}}
```

knowledge.type 从 Theory / Practical / Combat / Lore / Language 选
knowledge.mastery 从 初步了解 / 熟练 / 精通 / 完全解析 选
startingItems.type 从 Tool / Weapon / Clothing / Misc 选
"""

_QUESTION_SYSTEM = """你是一位专业的人格分析师，为AI游戏生成人格评估问卷。

问题设计铁律：
1. 每道题能揭示用户"不愿承认的真实倾向"——通过具体情境，而非直接问性格
2. 所有选项都必须是"正常人可能真的会选"的——没有明显的道德正确答案
3. 覆盖维度：真实压力反应、边界感、自我认知准确度、情绪触发点、对亲密关系的真实态度
4. 场景要具体、生活化，不要抽象

输出JSON数组，每题：
{"id": 序号, "question": "情境化的问题描述（不超过80字）", "type": "choice", "options": ["选项（20字以内，不加序号）", ...]}
"""


class GenerateProtagonistRequest(BaseModel):
    """LLM 生成主角请求"""
    mode: str = "background"       # background | quiz | quick
    # background 模式
    background: str = ""           # 用户填写的人物背景/设定
    # quiz 模式
    quiz_answers: list = []        # [{"question": "...", "answer": "..."}]
    # 共用偏好
    char_type: str = "本土"        # 本土 | 穿越者
    traversal_method: str = ""     # isekai | rebirth | possession | summoning | system | custom
    traversal_desc: str = ""       # 自定义穿越方式
    name_hint: str = ""            # 姓名提示（可选）
    gender_hint: str = ""          # 性别提示
    age_hint: str = ""             # 年龄提示
    # 是否同时写入 DB（false 则只返回预览 JSON）
    commit: bool = True
    world_key: str = ""
    starting_points: int = 0
    direct_character_data: Optional[dict] = None


def _build_traversal_block(char_type: str, method: str, desc: str) -> str:
    presets = {
        "rebirth":    "\u3010\u91cd\u751f\u3011\u4ee5\u5b8c\u6574\u8bb0\u5fc6\u5728\u672c\u4e16\u754c\u67d0\u4e00\u66f4\u65e9\u65f6\u95f4\u70b9\u91cd\u65b0\u51fa\u751f\uff0c\u751f\u7406\u8d77\u70b9\u4e0e\u672c\u571f\u4eba\u65e0\u5f02\uff0c\u4f46\u643a\u5e26\u5f02\u4e16\u754c\u8bb0\u5fc6\u548c\u77e5\u8bc6\u4f53\u7cfb\u3002",
        "possession": "\u3010\u593a\u820d/\u878d\u5408\u3011\u7075\u9b42/\u610f\u8bc6\u7a7f\u5165\u672c\u4e16\u754c\u5df2\u5b58\u5728\u4eba\u7269\u7684\u8eab\u4f53\uff0c\u7ee7\u627f\u90e8\u5206\u539f\u4e3b\u8bb0\u5fc6\u788e\u7247\uff0c\u4f46\u6838\u5fc3\u610f\u8bc6\u662f\u5f02\u4e16\u754c\u7684\u3002",
        "summoning":  "\u3010\u53ec\u5524/\u964d\u4e34\u3011\u4ee5\u73b0\u4ee3\u5730\u7403\u7684\u5b8c\u6574\u6210\u5e74\u8eab\u4efd\u88ab\u53ec\u5524\u81f3\u672c\u4e16\u754c\uff0c\u5916\u8c8c\u4f53\u8d28\u4e0e\u539f\u4e16\u754c\u5b8c\u5168\u4e00\u81f4\uff0c\u662f\u660e\u663e\u7684\u201c\u5916\u6765\u8005\u201d\u3002",
        "isekai":     "\u3010\u5f02\u4e16\u754c\u8f6c\u751f\uff08\u7ecf\u5178\u7248\uff09\u3011\u5728\u539f\u4e16\u754c\u6b7b\u4ea1\u540e\u4ee5\u539f\u8c8c\u5728\u672c\u4e16\u754c\u51fa\u751f/\u9192\u6765\uff0c\u4fdd\u6709\u5b8c\u6574\u8bb0\u5fc6\uff0c\u53ef\u80fd\u9644\u5e26\u201c\u8f6c\u751f\u795d\u798f\u201d\u3002",
        "system":     "\u3010\u7cfb\u7edf\u7a7f\u8d8a\u3011\u88ab\u672a\u77e5\u529b\u91cf\u643a\u5e26\u81f3\u672c\u4e16\u754c\uff0c\u540c\u65f6\u83b7\u5f97\u4e00\u4e2a\u201c\u7cfb\u7edf\u63d0\u793a\u754c\u9762\u201d\uff0c\u53ef\u80fd\u7ed9\u4e88\u5c11\u91cf\u521d\u59cb\u70b9\u6570\u6216\u65b0\u624b\u793c\u5305\u3002",
    }
    if char_type != "\u7a7f\u8d8a\u8005":
        return "\n==== \u3010\u89d2\u8272\u7c7b\u578b\uff1a\u672c\u571f\u3011 ====\n\u89d2\u8272\u662f\u672c\u4e16\u754c\u7684\u539f\u4f4f\u6c11\uff0c\u80cc\u666f\u3001\u77e5\u8bc6\u5e93\u3001\u80fd\u529b\u5747\u5e94\u4e0e\u672c\u4e16\u754c\u7684\u5386\u53f2\u548c\u6587\u5316\u73af\u5883\u5339\u914d\u3002\u4e0d\u8981\u6dfb\u52a0\u4efb\u4f55\u5f02\u4e16\u754c\u89c6\u89d2\u3002"

    block = presets.get(method, desc.strip() or presets["isekai"])
    return f"""
==== \u3010\u89d2\u8272\u7c7b\u578b\uff1a\u7a7f\u8d8a\u8005\u3011 ====
{block}

\u7a7f\u8d8a\u8005\u7279\u6b8a\u89c4\u5219\uff1a
- knowledge \u5b57\u6bb5\u5fc5\u987b\u5305\u542b1-2\u6761"\u73b0\u4ee3\u5730\u7403\u77e5\u8bc6"\u8282\u70b9
- \u5fc3\u7406\u5c42\u9762\u5fc5\u987b\u4f53\u73b0**\u6587\u5316\u9519\u4f4d**\u2014\u2014\u7528\u65e7\u4e16\u754c\u6846\u67b6\u7406\u89e3\u65b0\u4e16\u754c\uff0c\u4f1a\u4ea7\u751f\u8bef\u5224\u3001\u60ca\u8bb6\u6216\u8ba4\u77e5\u5931\u8c03
- \u7a7f\u8d8a\u524d\u5728\u539f\u4e16\u754c\u638c\u63e1\u7684\u6280\u80fd\u53ef\u4ee5\u4f5c\u4e3a knowledge \u6216\u521d\u59cb\u4f4e tier technique \u4fdd\u7559\uff0c\u4f46\u4e0d\u8d4b\u4e88\u8d85\u51e1\u529b\u91cf
"""



@router.get("/{novel_id}/generate-protagonist/questions")
async def get_generation_questions(novel_id: str, char_type: str = "本土", count: int = 12):
    """生成人格评估问卷（quiz 模式使用）"""
    from utils.llm_client import get_llm_client
    novel = await get_db().get_novel(novel_id)
    if not novel:
        raise HTTPException(404, "小说不存在")

    char_hint = ""
    if char_type == "穿越者":
        char_hint = "\n\n注意：本次创建的是穿越者（来自异世界的角色），请额外加入2-3道能揭示'跨文化适应/信息差'的问题。"

    llm = get_llm_client()
    try:
        result = await llm.chat_json(
            messages=[
                {"role": "system", "content": _QUESTION_SYSTEM},
                {"role": "user", "content": f"生成{count}道人格评估问题，覆盖：真实压力反应(3题)、人际边界(2题)、情绪触发点(2题)、自我认知(2题)、非理性倾向(2题)。直接输出JSON数组。{char_hint}"},
            ],
        )
        if not isinstance(result, list):
            result = result.get("questions", result.get("data", []))
        return {"questions": result, "count": len(result)}
    except Exception as e:
        raise HTTPException(500, f"生成题目失败: {e}")


@router.post("/{novel_id}/generate-protagonist")
async def generate_protagonist(
    novel_id: str,
    req: GenerateProtagonistRequest,
    db: Database = Depends(_db),
):
    """
    LLM 生成完整主角档案。
    mode=background: 根据用户填写的背景描述生成
    mode=quiz:       根据人格问卷回答生成
    mode=quick:      根据少量偏好快速生成
    commit=True: 同时写入 DB（init_protagonist + 写入心理模型/属性等）
    """
    import json as _json
    import re

    novel = await db.get_novel(novel_id)
    if not novel:
        raise HTTPException(404, "小说不存在")

    from utils.llm_client import get_llm_client
    llm = get_llm_client()

    if req.direct_character_data:
        char_data = req.direct_character_data
    else:
        system_prompt = _CHAR_GEN_SYSTEM.format(
            anti_rational=_ANTI_RATIONAL,
            tier_ref=_TIER_REF,
        ) + _build_traversal_block(req.char_type, req.traversal_method, req.traversal_desc)

        # 构建 user prompt
        extras = ""
        if req.name_hint:   extras += f"\n姓名设定：{req.name_hint}"
        if req.gender_hint: extras += f"\n性别设定：{req.gender_hint}"
        if req.age_hint:    extras += f"\n年龄范围：{req.age_hint}"

        if req.mode == "quiz" and req.quiz_answers:
            qa_text = "\n\n".join(
                f"[Q{i+1}] {item.get('question','')}\n[回答] {item.get('answer','（跳过）')}"
                for i, item in enumerate(req.quiz_answers)
            )
            user_prompt = (
                f"根据以下人格评估问答，创作一个有真实人味的游戏主角，同时生成完整的初始游戏面板数据。\n\n"
                f"重要：不要把答案字面内容搬进人物里，而是通过答案揭示的倾向进行心理推断。"
                f"重点关注：回答之间的矛盾之处、用词里暴露的情绪、回避的方式。\n{extras}\n\n{qa_text}"
            )
        elif req.mode == "quick":
            user_prompt = (
                f"根据以下简要偏好，创作一个有趣、真实的游戏主角并生成完整面板数据。\n"
                f"偏好：{req.background or '普通现代人，有些许问题，但也有自己的坚持'}{extras}"
            )
        else:  # background
            user_prompt = (
                f"根据以下人物背景/设定，创作完整的游戏主角档案，同时生成符合数据模板的初始游戏面板数据。\n\n"
                f"重要提醒：\n"
                f"- 背景里没写清楚的地方，用合理的心理推断填充，不要用完美的答案填充\n"
                f"- 从背景经历推断心理创伤和行为模式，而不是直接复述背景内容\n"
                f"- 忠实原则：输入中已有的性格/缺点/渴望/恐惧，直接具体化，不要重新发明{extras}\n\n"
                f"---\n{req.background or '普通人类，无特殊背景，你来自由决定一个有趣的普通人故事'}"
            )

        # 调用 LLM
        try:
            raw = await llm.chat(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user",   "content": user_prompt},
                ],
                max_tokens=4096,
            )
        except Exception as e:
            raise HTTPException(500, f"LLM 调用失败: {e}")

        # 解析 JSON
        char_data = None
        m = re.search(r'```(?:json)?\s*(\{[\s\S]+?\})\s*```', raw, re.DOTALL)
        if m:
            try:
                char_data = _json.loads(m.group(1))
            except Exception:
                pass
        if char_data is None:
            try:
                char_data = _json.loads(raw)
            except Exception:
                raise HTTPException(500, f"LLM 返回内容无法解析为 JSON，原始内容：{raw[:500]}")

    if not req.commit:
        return {"character": char_data, "committed": False}

    # ── 写入数据库 ──
    name = char_data.get("name", req.name_hint or "无名者")

    # 1. 初始化主角基础行
    await db.init_protagonist(
        novel_id=novel_id,
        name=name,
        world_key=req.world_key,
        attr_schema_id=novel.get("attr_schema_id", "standard_10d"),
    )

    # 2. 更新属性
    attrs = char_data.get("attributes", {})
    if attrs:
        await db.update_protagonist_state(novel_id, attributes=attrs)

    # 3. 写入完整角色档案（外貌/背景/性格等文字字段）
    profile_fields = {}
    for field in ("gender", "age", "identity", "height", "weight", "alignment",
                  "appearance", "clothing", "background"):
        val = char_data.get(field, "")
        if val:
            profile_fields[field] = str(val)
    for field in ("personality", "flaws", "desires", "fears", "quirks", "traits"):
        val = char_data.get(field, [])
        if val:
            profile_fields[field] = val
    if profile_fields:
        await db.update_protagonist_state(novel_id, **profile_fields)

    # 4. 写入心理模型 JSON
    psyche = char_data.get("psyche_model", {})
    if psyche:
        await db.update_protagonist_state(novel_id, psyche_model_json=psyche)

    # 5. 写入知识图谱
    knowledge = char_data.get("knowledge", [])
    if knowledge:
        await db.update_protagonist_state(novel_id, knowledge_scope=knowledge)

    # 6. 写入能量池（包含 current/max/regen）
    for ps in char_data.get("powerSources", []):
        pool_name = ps.get("poolName", ps.get("name", ""))
        if pool_name:
            await db.register_energy_pool(novel_id, {
                "name": pool_name,
                "max": ps.get("poolMax", 100),
                "value": ps.get("poolMax", 100),  # 初始满值
                "regen": ps.get("poolRegen", ""),
                "description": ps.get("desc", ""),
            })

    # 6. 积分
    if req.starting_points > 0:
        await db.add_points(novel_id, req.starting_points)

    # 7. 写入能力和物品到 owned_items
    import uuid
    def _make_item(item_type: str, item_data: dict, default_tier: int):
        return {
            "id": str(uuid.uuid4()),
            "novel_id": novel_id,
            "item_key": item_data.get("name", item_data.get("poolName", "Unknown")),
            "item_name": item_data.get("name", item_data.get("poolName", "Unknown")),
            "item_type": item_type,
            "source_world": req.world_key or "本源",
            "tier": item_data.get("tier", default_tier),
            "tier_sub": "M",
            "final_tier": item_data.get("tier", default_tier),
            "final_sub": "M",
            "description": item_data.get("desc", ""),
            "payload": item_data,
            "is_active": 1,
            "is_equipped": 1,
            "can_unequip": 1 if item_type == "Inventory" else 0
        }

    for it in char_data.get("startingItems", []):
        await db.insert_owned_item(_make_item("Inventory", it, 0))
    for it in char_data.get("passiveAbilities", []):
        await db.insert_owned_item(_make_item("PassiveAbility", it, 1))
    for it in char_data.get("techniques", []):
        await db.insert_owned_item(_make_item("ApplicationTechnique", it, 0))
    for it in char_data.get("powerSources", []):
        await db.insert_owned_item(_make_item("PowerSource", it, 0))

    protagonist = await db.get_protagonist_state(novel_id)

    # 8. 写入关联 NPC（背景中提及的人物）并初始化记忆图谱
    relationships = char_data.get("relationships", [])
    generated_npcs = []
    if relationships:
        from memory.graph import graph_manager
        from memory.schema import MemoryNode, NodeType, RelationType
        import uuid as _uuid

        # 先获取或创建主角的 CHARACTER 节点
        graph = graph_manager.get(novel_id)
        protagonist_node_id = None
        for nid, data in graph._G.nodes(data=True):
            if (data.get("node_type") == NodeType.CHARACTER.value
                    and data.get("extra", {}).get("is_protagonist")):
                protagonist_node_id = nid
                break
        if not protagonist_node_id:
            import uuid as _uuid2
            from datetime import datetime as _dt, timezone as _tz
            p_node = MemoryNode(
                node_id=str(_uuid2.uuid4()),
                novel_id=novel_id,
                node_type=NodeType.CHARACTER,
                world_key=req.world_key,
                title=name,
                content=f"{name}：{char_data.get('identity', '')}。{char_data.get('background', '')[:100]}",
                summary=char_data.get('background', '')[:100],
                confidence=1.0,
                importance=1.0,
                extra={"is_protagonist": True, "relationship_map": {}},
                created_at=_dt.now(_tz.utc).isoformat(),
                updated_at=_dt.now(_tz.utc).isoformat(),
            )
            await graph_manager.add_node(novel_id, p_node)
            protagonist_node_id = p_node.node_id

        bidirectional = RelationType.emotional_types()

        for rel in relationships[:5]:
            npc_name = rel.get("name", "").strip()
            if not npc_name:
                continue
            emotion_type_str = rel.get("emotion_type", "related")
            try:
                emotion_rel = RelationType(emotion_type_str)
            except ValueError:
                emotion_rel = RelationType.KNOWS

            # 写入 NPC 档案
            try:
                await db.upsert_npc(
                    novel_id=novel_id,
                    name=npc_name,
                    data={
                        "npc_type":        rel.get("npc_type", "neutral"),
                        "world_key":       req.world_key,
                        "trait_lock":      rel.get("trait_lock", []),
                        "knowledge_scope": rel.get("knowledge_scope", []),
                        "capability_cap":  {"tier": 0, "tier_sub": "M"},
                        "initial_affinity": int(rel.get("affinity", 50)),
                        "loyalty_type":    rel.get("loyalty_type", ""),
                        "companion_slot":  0,
                        "psyche_model": {
                            "background":              rel.get("background", ""),
                            "appearance":              rel.get("appearance", ""),
                            "relation_to_protagonist": rel.get("relation", ""),
                            "emotion_type":            emotion_type_str,
                            "emotion_tags":            rel.get("emotion_tags", []),
                        },
                    },
                )
                generated_npcs.append(npc_name)
            except Exception as _npc_err:
                pass

            # 在图中创建 NPC CHARACTER 节点
            from datetime import datetime as _dt2, timezone as _tz2
            npc_node_id = str(_uuid.uuid4())
            npc_node = MemoryNode(
                node_id=npc_node_id,
                novel_id=novel_id,
                node_type=NodeType.CHARACTER,
                world_key=req.world_key,
                title=npc_name,
                content=f"{npc_name}：{rel.get('relation', '')}。{rel.get('background', '')}",
                summary=rel.get("background", "")[:80],
                confidence=1.0,
                importance=0.8,
                extra={
                    "is_protagonist": False,
                    "npc_type": rel.get("npc_type", "neutral"),
                    "appearance": rel.get("appearance", ""),
                    "relationship_map": {name: rel.get("relation", "")},
                },
                created_at=_dt2.now(_tz2.utc).isoformat(),
                updated_at=_dt2.now(_tz2.utc).isoformat(),
            )
            await graph_manager.add_node(novel_id, npc_node)

            # 建立情感边（主角 → NPC）
            affinity_val = int(rel.get("affinity", 50))
            emotion_tags = rel.get("emotion_tags", [])
            relation_label = rel.get("relation", "")
            edge_attrs = {
                "affinity": affinity_val,
                "emotion_tags": _json.dumps(emotion_tags, ensure_ascii=False),
                "relation_label": relation_label,
            }
            await graph_manager.add_edge(
                novel_id, protagonist_node_id, npc_node_id, emotion_rel, **edge_attrs
            )
            # 双向关系类型自动建反向边
            if emotion_rel in bidirectional:
                await graph_manager.add_edge(
                    novel_id, npc_node_id, protagonist_node_id, emotion_rel, **edge_attrs
                )

    return {
        "character":      char_data,
        "protagonist":    protagonist,
        "generated_npcs": generated_npcs,
        "committed":      True,
        "message":        f"主角「{name}」已生成并初始化，关联人物: {len(generated_npcs)} 个",
    }


# ── 正文重置（无快照时的兜底方案）──────────────────────────────────────────

@router.post("/{novel_id}/reset-content", status_code=200)
async def reset_novel_content(novel_id: str, db: Database = Depends(_db)):
    """
    硬重置：清空小说正文（消息/快照/伏笔/成长/积分/物品），
    保留主角档案（姓名/外貌/性格）和 NPC 档案。
    用于无快照时的完全回归初始状态。
    """
    novel = await db.get_novel(novel_id)
    if not novel:
        raise HTTPException(status_code=404, detail="小说不存在")

    deleted: dict[str, int] = {}

    async def _del(table: str):
        row = await db._fetchone(
            f"SELECT COUNT(*) as c FROM {table} WHERE novel_id=?", (novel_id,)
        )
        deleted[table] = (row or {}).get("c", 0)
        await db._exec(f"DELETE FROM {table} WHERE novel_id=?", (novel_id,))

    for t in ("messages", "turn_snapshots", "narrative_hooks", "chapters",
              "growth_records", "growth_event_records", "medals",
              "achievements", "exchange_log", "owned_items"):
        await _del(t)

    # 重置主角动态字段（保留档案字段）
    await db._exec(
        "UPDATE protagonist_state SET "
        "  points=0, tier=0, tier_sub='M', "
        "  status_effects='[]', energy_pools='{}', "
        "  updated_at=datetime('now') "
        "WHERE novel_id=?",
        (novel_id,),
    )

    # 清理记忆图谱（非 CHARACTER 节点）
    graph_removed = 0
    try:
        from memory.graph import graph_manager
        from memory.schema import NodeType
        graph = graph_manager.get(novel_id)
        to_remove = [
            nid for nid, data in graph._G.nodes(data=True)
            if data.get("node_type") != NodeType.CHARACTER.value
        ]
        graph_removed = await graph_manager.remove_nodes(novel_id, to_remove)
    except Exception:
        pass

    protagonist = await db.get_protagonist_state(novel_id)
    npc_count = (await db._fetchone(
        "SELECT COUNT(*) as c FROM npc_profiles WHERE novel_id=?", (novel_id,)
    ) or {}).get("c", 0)

    return {
        "message":            "正文已重置，主角档案与NPC保留",
        "deleted":            deleted,
        "graph_nodes_removed": graph_removed,
        "protagonist_name":   protagonist.get("name") if protagonist else None,
        "npc_preserved":      npc_count,
    }
