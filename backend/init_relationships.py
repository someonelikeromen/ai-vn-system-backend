"""
init_relationships.py
直接调用系统内部逻辑，为丹童浩一初始化完整的人际关系网络
无需启动 FastAPI 服务
"""
import asyncio
import sys
import os
import json

# 强制 UTF-8 输出（避免 GBK 控制台乱码）
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.dirname(__file__))

NOVEL_ID = "d7830720-bb9a-41d3-9009-f38133d564c1"
PROTAGONIST_NAME = "丹童浩一"

# ── 根据背景定义的完整关系网 ──────────────────────────────────────────────────
RELATIONSHIPS = [
    {
        "name": "春日野穹",
        "relation": "义妹，幼年一同相依为命，逐渐产生了超越兄妹的复杂情感",
        "emotion_type": "mixed",          # 亲情+爱情混合
        "emotion_tags": ["亲情", "依赖", "暧昧", "羁绊"],
        "affinity": 98,
        "loyalty_type": "血缘情感（义）+ 情感联结",
        "npc_type": "companion",
        "trait_lock": [
            "外表独立内心依赖",
            "对浩一存在特殊感情",
            "因父母失事留有心理阴影",
            "已开解但仍有深深依赖",
            "坦率直接不善遮掩",
        ],
        "knowledge_scope": [
            "浩一的全部日常",
            "浩一的轻小说创作",
            "浩一的健身习惯",
            "浩一的投资资产",
            "浩一的二次元爱好",
            "约定的内容",
        ],
        "background": (
            "春日野家次女，父母收养了浩一并视如己出。"
            "父母与兄长春日野悠在一次旅行事故中全部遇难，"
            "此后只有她和浩一相依为命。"
            "面对觊觎遗产的亲戚，浩一选择独立带着她生活，"
            "照顾与陪伴中两人建立起超越义兄妹的深厚羁绊。"
            "对浩一有着程度深入的依赖与复杂感情，两人有特殊约定。"
        ),
        "appearance": "银发蓝瞳，外表清丽可爱，气质中带着些许冷清与孤傲，私下对浩一截然不同",
        "tier": 0,
    },
    {
        "name": "黑猫五更琉璃",
        "relation": "网友，网游伙伴，高一时结识，目前最密切的朋友之一",
        "emotion_type": "friendship",
        "emotion_tags": ["友情", "趣味相投", "网友情谊"],
        "affinity": 75,
        "loyalty_type": "情感联结（共同爱好）",
        "npc_type": "companion",
        "trait_lock": [
            "傲娇中二属性浓厚",
            "对网游和轻小说有强烈热情",
            "私下是五更家闺女但不常提",
            "对浩一的轻小说极为欣赏",
            "线上比线下更放得开",
        ],
        "knowledge_scope": [
            "浩一的轻小说笔名和作品",
            "浩一的游戏风格和ID",
            "浩一的部分二次元喜好",
        ],
        "background": (
            "高一时在网络上结识浩一，以网游伙伴和同为小说爱好者的身份成为密友。"
            "中二傲娇，在现实生活中是五更家的千金，但更享受网络世界中的自在。"
            "对浩一的轻小说创作（斗破苍穹、遮天等）极为欣赏，视其为难得的知音。"
        ),
        "appearance": "黑发红瞳，外表清冷，有中二病倾向，私下话多且可爱",
        "tier": 0,
    },
    {
        "name": "山田妖精",
        "relation": "轻小说作家前辈，好友，通过创作圈认识",
        "emotion_type": "friendship",
        "emotion_tags": ["友情", "业界前辈", "共同爱好"],
        "affinity": 68,
        "loyalty_type": "情感联结（创作圈同好）",
        "npc_type": "companion",
        "trait_lock": [
            "业内轻小说作家",
            "对浩一的作品有高度评价",
            "性格随和，愿意提携后辈",
            "对浩一知根知底（创作层面）",
        ],
        "knowledge_scope": [
            "浩一的写作风格",
            "浩一在轻小说圈的名气",
            "浩一已半退隐的状态",
        ],
        "background": (
            "轻小说圈内小有名气的作家，因作品相识后成为浩一的好友。"
            "见证了浩一从斗破苍穹到遮天的创作历程，"
            "也了解浩一选择半退隐享受青春的决定。"
        ),
        "appearance": "普通外貌，但谈起创作时眼睛里有光",
        "tier": 0,
    },
    {
        "name": "平冢静",
        "relation": "班主任老师，对浩一有基本了解",
        "emotion_type": "affiliated",
        "emotion_tags": ["师生关系", "关照"],
        "affinity": 55,
        "loyalty_type": "职责关系",
        "npc_type": "neutral",
        "trait_lock": [
            "毒舌但关心学生",
            "单身情结略有敏感",
            "对有特点的学生格外上心",
            "对浩一的成熟度有所注意",
        ],
        "knowledge_scope": [
            "浩一的学业状态",
            "浩一的轻小说家身份（部分）",
        ],
        "background": (
            "担任浩一所在班级的班主任，性格毒舌却真心关怀学生。"
            "注意到浩一与普通高中生不同的成熟气质，"
            "也知道其轻小说家的身份，对其半退隐状态暗自关注。"
        ),
        "appearance": "成熟干练的女教师，偶尔流露出单身的落寞感",
        "tier": 0,
    },
    {
        "name": "四宫辉夜",
        "relation": "学生会长，有所关注但尚未深交",
        "emotion_type": "knows",
        "emotion_tags": ["同校", "有所耳闻"],
        "affinity": 40,
        "loyalty_type": "利益无关",
        "npc_type": "neutral",
        "trait_lock": [
            "骄傲冷淡但心思细腻",
            "四宫家千金，身份高贵",
            "对不符合预期的人物会产生好奇",
            "不轻易展示弱点",
        ],
        "knowledge_scope": [
            "浩一的轻小说家声望（可能知晓）",
            "浩一在学校中的淡然存在感",
        ],
        "background": (
            "学校学生会长，四宫家嫡女，才貌出众性格高傲。"
            "尚未与浩一有深度交集，但浩一的淡然气质和创作名声"
            "在她的观察范围之内，对其存在有一定关注。"
        ),
        "appearance": "黑长直，气质冷艳高贵，举手投足皆是大家风范",
        "tier": 0,
    },
]

async def main():
    # 初始化系统
    from config import get_settings
    from db.models import init_db
    from db.queries import init_db_instance, get_db

    settings = get_settings()
    print(f"[Init] DB: {settings.db_path}")
    await init_db(str(settings.db_path_resolved))
    db = await init_db_instance(str(settings.db_path_resolved))

    from memory.graph import graph_manager
    from memory.schema import MemoryNode, NodeType, RelationType

    # graph_manager 懒加载，首次 get() 时自动初始化
    graph_manager.get(NOVEL_ID)
    print(f"[Init] 记忆图谱就绪，novel_id={NOVEL_ID}")

    # ── 1. 确认主角节点 ──────────────────────────────────────────────
    protagonist = await db.get_protagonist_state(NOVEL_ID)
    if not protagonist:
        print("[ERROR] 主角不存在！请先生成主角。")
        return

    print(f"[主角] {protagonist['name']} ✓")

    # 在图谱中查找或创建主角节点
    import uuid
    from datetime import datetime, timezone

    graph = graph_manager.get(NOVEL_ID)
    protagonist_node_id = None
    for nid, data in graph._G.nodes(data=True):
        if (data.get("node_type") == NodeType.CHARACTER.value
                and data.get("extra", {}).get("is_protagonist")):
            protagonist_node_id = nid
            break

    if not protagonist_node_id:
        p_node = MemoryNode(
            node_id=str(uuid.uuid4()),
            novel_id=NOVEL_ID,
            node_type=NodeType.CHARACTER,
            world_key=protagonist.get("world_key", ""),
            title=PROTAGONIST_NAME,
            content=(
                f"{PROTAGONIST_NAME}：前世社畜，业余爱好二次元，单亲家庭出身。"
                f"重生为丹童浩一，被春日野家收养，后成为春日野穹的义兄。"
                f"凭借前世记忆投资崛起，写作斗破苍穹等轻小说小有名气后半退隐。"
                f"习剑（活杀逸刀流），健身养生，享受青春生活。"
            ),
            summary="重生社畜，义兄，轻小说家（半退隐），活杀逸刀流学员，成熟稳重",
            confidence=1.0,
            importance=1.0,
            extra={
                "is_protagonist": True,
                "relationship_map": {},
                "background_tags": [
                    "重生者", "穿越者", "轻小说家（半退隐）",
                    "活杀逸刀流", "投资者", "义兄", "二次元爱好者",
                    "健身", "成熟稳重", "不傲慢融入世界",
                ],
            },
            created_at=datetime.now(timezone.utc).isoformat(),
            updated_at=datetime.now(timezone.utc).isoformat(),
        )
        await graph_manager.add_node(NOVEL_ID, p_node)
        protagonist_node_id = p_node.node_id
        print(f"[图谱] 创建主角节点 {protagonist_node_id[:8]}")
    else:
        print(f"[图谱] 主角节点已存在 {protagonist_node_id[:8]}")

    # ── 2. 批量创建 NPC + 关系边 ──────────────────────────────────────
    bidirectional = RelationType.emotional_types()
    created_npcs = []

    for rel in RELATIONSHIPS:
        npc_name = rel["name"]
        print(f"\n[NPC] 处理: {npc_name}")

        # 写入/更新 NPC 档案
        try:
            await db.upsert_npc(
                novel_id=NOVEL_ID,
                name=npc_name,
                data={
                    "npc_type":        rel["npc_type"],
                    "world_key":       protagonist.get("world_key", ""),
                    "trait_lock":      rel["trait_lock"],
                    "knowledge_scope": rel["knowledge_scope"],
                    "capability_cap":  {"tier": rel.get("tier", 0), "tier_sub": "M"},
                    "initial_affinity": rel["affinity"],
                    "loyalty_type":    rel["loyalty_type"],
                    "companion_slot":  1 if rel["npc_type"] == "companion" else 0,
                    "psyche_model": json.dumps({
                        "background":              rel["background"],
                        "appearance":              rel["appearance"],
                        "relation_to_protagonist": rel["relation"],
                        "emotion_type":            rel["emotion_type"],
                        "emotion_tags":            rel["emotion_tags"],
                    }, ensure_ascii=False),
                },
            )
            print(f"  ✓ NPC档案已写入")
        except Exception as e:
            print(f"  ✗ NPC档案写入失败: {e}")

        # 在图谱中创建 NPC CHARACTER 节点
        # 先检查是否已存在
        npc_node_id = None
        for nid, data in graph._G.nodes(data=True):
            if (data.get("node_type") == NodeType.CHARACTER.value
                    and data.get("title") == npc_name):
                npc_node_id = nid
                break

        if not npc_node_id:
            npc_node_id = str(uuid.uuid4())
            npc_node = MemoryNode(
                node_id=npc_node_id,
                novel_id=NOVEL_ID,
                node_type=NodeType.CHARACTER,
                world_key=protagonist.get("world_key", ""),
                title=npc_name,
                content=f"{npc_name}：{rel['relation']}。{rel['background']}",
                summary=rel["background"][:100],
                confidence=1.0,
                importance=0.85,
                extra={
                    "is_protagonist": False,
                    "npc_type": rel["npc_type"],
                    "appearance": rel["appearance"],
                    "relationship_map": {PROTAGONIST_NAME: rel["relation"]},
                    "emotion_type": rel["emotion_type"],
                    "emotion_tags": rel["emotion_tags"],
                    "affinity": rel["affinity"],
                },
                created_at=datetime.now(timezone.utc).isoformat(),
                updated_at=datetime.now(timezone.utc).isoformat(),
            )
            await graph_manager.add_node(NOVEL_ID, npc_node)
            print(f"  ✓ 图节点已创建 {npc_node_id[:8]}")
        else:
            print(f"  ✓ 图节点已存在 {npc_node_id[:8]}")

        # 建立情感边
        try:
            emotion_rel_str = rel["emotion_type"]
            try:
                emotion_rel = RelationType(emotion_rel_str)
            except ValueError:
                emotion_rel = RelationType.KNOWS

            edge_attrs = {
                "affinity": rel["affinity"],
                "emotion_tags": json.dumps(rel["emotion_tags"], ensure_ascii=False),
                "relation_label": rel["relation"],
            }

            # 正向边：主角 → NPC
            ok1 = await graph_manager.add_edge(
                NOVEL_ID, protagonist_node_id, npc_node_id, emotion_rel, **edge_attrs
            )
            print(f"  ✓ 正向边 ({emotion_rel_str}) {'已建立' if ok1 else '建立失败'}")

            # 双向关系自动建反向边
            if emotion_rel in bidirectional:
                ok2 = await graph_manager.add_edge(
                    NOVEL_ID, npc_node_id, protagonist_node_id, emotion_rel, **edge_attrs
                )
                print(f"  ✓ 反向边 ({emotion_rel_str}) {'已建立' if ok2 else '建立失败'}")

        except Exception as e:
            print(f"  ✗ 关系边建立失败: {e}")

        created_npcs.append(npc_name)

    # ── 3. 输出关系网摘要 ─────────────────────────────────────────────
    print("\n" + "="*60)
    print(f"[完成] 人际关系网络初始化完成！")
    print(f"主角: {PROTAGONIST_NAME}")
    print(f"关系数量: {len(created_npcs)}")
    for r in RELATIONSHIPS:
        tag_str = " / ".join(r["emotion_tags"])
        print(f"  {'★' if r['npc_type']=='companion' else '○'} {r['name']:<10} "
              f"好感:{r['affinity']:3d}  [{r['emotion_type']:12s}] {tag_str}")

    stats = graph_manager.get_stats(NOVEL_ID)
    print(f"\n[图谱] 节点数: {stats.get('node_count', '?')}  边数: {stats.get('edge_count', '?')}")

    # ── 4. 验证 NPC 档案 ──────────────────────────────────────────────
    npc_rows = await db._fetchall(
        "SELECT name, npc_type, initial_affinity FROM npc_profiles WHERE novel_id=? ORDER BY initial_affinity DESC",
        (NOVEL_ID,)
    )
    print(f"\n[数据库] NPC档案 ({len(npc_rows)} 条):")
    for row in npc_rows:
        print(f"  {row['name']:<12} {row['npc_type']:<10} 好感={row['initial_affinity']}")


if __name__ == "__main__":
    asyncio.run(main())
