"""
generate_opening.py
直接向数据库写入开局内容，以 assistant 消息形式插入，
包含：早晨起床场景 + 上课时系统觉醒
同时插入第一个 narrative_hook 和 protagonist_state 更新
"""
import asyncio, sys, os, json, uuid
from datetime import datetime, timezone

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')
sys.path.insert(0, os.path.dirname(__file__))

NOVEL_ID = "d7830720-bb9a-41d3-9009-f38133d564c1"

# ── 开局正文（完整的第一章开幕）────────────────────────────────────────────────
OPENING_TEXT = """
【第一章  破晓】

──

清晨六点四十分。

闹钟响的前两分钟，丹童浩一就已经醒了。

他的眼睛睁开，凝视着天花板上那道熟悉的斜纹裂缝——三年了，每次他都想着等存款再多一点再修，然后每次都忘了。被子轻轻起伏着，一种温热的重量压在他右侧。

他低头。

春日野穹蜷缩在他旁边，黑色羽绒被覆到下巴，银发散乱在枕边，睫毛整齐地垂着，像一幅安静到过分的画。昨夜她半夜摸过来的，理由是"做了不好的梦"，他没问是什么梦，她也没说，就这样睡过去了。

浩一没有立刻起身。

他就这么看了她几秒钟，然后轻手轻脚地从被子里抽出手臂，把她这侧的被角顺势掖了掖，起身。

地板是冷的。

他套上拖鞋，绕过放在地上的书包，走进盥洗室，在镜子前对着自己看了一眼——黑色碎发，稍微凌乱，带着睡眠后的折痕，比去年又高了一点点。

185cm。

……有时候他自己都觉得奇异。这张脸，这具身体，都是别人的，却又确实是他的。那个在上海租着月租1500的单间、泡着碗面看番、在末班地铁上打盹的男人，和现在这个站在精装修卫生间里的高中生，理论上是同一个人。

他抓起牙刷，开始刷牙。

*

晨练是雷打不动的习惯。

小区楼下，晨雾还没散尽，他跑了三公里，又做了一组拉伸和引体向上。没有耳机，只有自己的呼吸声和路边麻雀偶尔的叫声。他不喜欢跑步时听东西——这是少数他真正能"清空大脑"的时刻。

两世加起来，能让他真正"清空"的时刻很少。

回到家，穹已经坐在餐桌前了。她换了校服，头发束起，在喝热牛奶，杯子捧在手里，眼睛还有点没睁开的样子。她看了他一眼，又移开，像什么都没发生过。

"吃饭了，"她说，声音带着刚睡醒的沙哑。

桌上有两个煎蛋、切开的吐司、一碟咸鱼，都是她弄的。

浩一洗了手，在她对面坐下。

"几点睡着的？"

"不知道。"停顿。"……你走了之后。"

他没有追问。拿起筷子，低头吃饭。

窗外，4月的早晨慢慢亮起来，把光从窗帘缝里漏进来，落在她的头发上，银色带着一点淡淡的金。

──

上课的时间是八点整。

他和穹一起出门，到了路口分开——她的班级在二楼，他在四楼，平时没什么交集。她背着书包走进人群，没有回头，他站在原地看了一秒，转身，跟着学生流上了楼梯。

教室里已经有一半人到了。

靠窗的座位，他坐下，把书包挂在椅背上，拿出昨天没改完的日语练习册。从这个角度能看到操场，还有远处建筑群的轮廓。

第一节，古典文学。

讲的是《徒然草》，老师声音平稳，像在背书，底下有三个人已经在低头——浩一翻着页，偶尔在空白处写两个字，脑子转到了别处。

投资组合。

那家做虚拟现实的小公司上个月完成了A轮，他在两年前就押进去了。还有一个做AI芯片周边的……

──

十点十七分。

没有任何征兆。

他正在听第二节，数学，老师在黑板上写着一道行列式，粉笔声很清脆。他的手肘撑在桌上，脑子有一瞬的恍惚——不是睡意，是别的什么，像什么东西从他胸腔深处被拔起来。

然后一道光。

不是真正的光，但他的大脑把它记录成光——在他的视野正中央，一个半透明的界面，突然出现了。

```
════════════════════════════════
      S Y S T E M   ONLINE
════════════════════════════════

  ▸ 宿主识别中…………………… [完成]
  ▸ 宿慧校验中…………………… [通过]
  ▸ 初始化数据导入…………… [完成]

  ✦ 宿主：丹童浩一
  ✦ 当前阶段：M 阶（基础觉醒）
  ✦ 积分：0
  ✦ 层级标识：观察者模式（未授权）

  系统初次上线。
  欢迎，宿主。

════════════════════════════════
```

他的手指在桌面上轻轻收紧。

旁边的同学没有任何反应，老师还在推导行列式，窗外的鸟还在叫，世界完全没有改变。

只有他看见了。

——*当然*，他想，用比自己预想的更加平静的心情，*当然会有这个。*

他缓缓呼出一口气，用了不到三秒钟调整自己的表情回到正常状态，然后在草稿纸的角落，写下了三个字：

「系统来了。」

他盯着这三个字看了一秒，在旁边画了一个小小的圆圈，若有所思地把笔帽套回去。

课还在继续。行列式还在黑板上。

他重新举起眼睛，看着老师，面色平静，和往常没有一点区别。

*
*
*

只是，心里某个地方，有什么东西，安静地、确定地，动了一下。

──

【系统提示：觉醒完成。初始面板已开启。请于今日放学后完成首次状态检视。】
""".strip()

async def main():
    from config import get_settings
    from db.models import init_db
    from db.queries import init_db_instance

    s = get_settings()
    await init_db(str(s.db_path_resolved))
    db = await init_db_instance(str(s.db_path_resolved))

    now_iso = datetime.now(timezone.utc).isoformat()

    # ── 1. 插入开局消息 ──────────────────────────────────────────────
    # 先插入 user 的"开始"消息
    await db._exec(
        "INSERT INTO messages (novel_id, role, raw_content, display_content, message_order, created_at) "
        "VALUES (?, 'user', ?, ?, 1, ?)",
        (NOVEL_ID, "从今天早晨开始。", "从今天早晨开始。", now_iso)
    )

    # 插入 assistant 的开局正文
    await db._exec(
        "INSERT INTO messages (novel_id, role, raw_content, display_content, message_order, created_at) "
        "VALUES (?, 'assistant', ?, ?, 2, ?)",
        (NOVEL_ID, OPENING_TEXT, OPENING_TEXT, now_iso)
    )

    print(f"✓ 消息已写入 (user: 1, assistant: 2)")

    # ── 2. 更新主角状态（觉醒后）────────────────────────────────────
    awakening_effect = json.dumps([
        {
            "name": "系统觉醒",
            "type": "passive",
            "duration": "永久",
            "effect": "M阶观察者模式已激活，面板初次上线"
        }
    ], ensure_ascii=False)

    await db._exec(
        "UPDATE protagonist_state SET status_effects=?, updated_at=? WHERE novel_id=?",
        (awakening_effect, now_iso, NOVEL_ID)
    )
    print("✓ 主角状态已更新（系统觉醒效果已添加）")

    # ── 3. 写入初始 narrative_hook ──────────────────────────────────
    await db._exec(
        "INSERT INTO narrative_hooks "
        "(novel_id, description, status, urgency, seeded_at_chapter) "
        "VALUES (?, ?, 'active', 2, 0)",
        (
            NOVEL_ID,
            "系统第一次上线，宿主尚在「观察者模式」，功能未完全授权。系统自称「初次上线」，其真实来源和意图成谜。",
        )
    )
    print(f"✓ 伏笔已插入：系统来源之谜")

    # ── 4. 写入图谱记忆节点（觉醒事件）─────────────────────────────
    from memory.graph import graph_manager
    from memory.schema import MemoryNode, NodeType, RelationType

    event_node = MemoryNode(
        node_id=str(uuid.uuid4()),
        novel_id=NOVEL_ID,
        node_type=NodeType.EVENT,
        world_key="综漫日常+灵异/灵气复苏",
        title="系统初次觉醒",
        content=(
            "高二上学期某日上午十点十七分，丹童浩一在数学课上经历了系统首次上线。"
            "无任何征兆，半透明界面突然出现，显示M阶觉醒、积分0、观察者模式。"
            "周围人无感知。浩一用约三秒时间平复情绪，在草稿纸上写下「系统来了」，"
            "随后若无其事地继续听课。"
        ),
        summary="数学课上，系统首次觉醒，丹童浩一以异常平静的态度接受了这一事实",
        confidence=1.0,
        importance=1.0,
        extra={
            "event_type": "awakening",
            "location": "教室",
            "time": "上午10:17",
            "participants": ["丹童浩一"],
            "tags": ["觉醒", "系统上线", "M阶", "观察者模式"],
        },
        created_at=now_iso,
        updated_at=now_iso,
    )
    await graph_manager.add_node(NOVEL_ID, event_node)
    print(f"✓ 图谱事件节点已创建：系统初次觉醒 ({event_node.node_id[:8]})")

    # 早晨与穹的日常节点
    morning_node = MemoryNode(
        node_id=str(uuid.uuid4()),
        novel_id=NOVEL_ID,
        node_type=NodeType.EVENT,
        world_key="综漫日常+灵异/灵气复苏",
        title="清晨日常：穹的半夜探床",
        content=(
            "早晨六点四十分，浩一在闹钟前自然醒，发现穹在半夜摸过来同床入眠（理由是做了不好的梦）。"
            "浩一没有追问，为她掖好被角，悄悄起身晨练。"
            "早饭由穹准备，两人安静吃饭，话少而自然。"
        ),
        summary="穹夜间探床，清晨两人安静共食，日常羁绊的缩影",
        confidence=1.0,
        importance=0.6,
        extra={
            "event_type": "daily",
            "location": "家",
            "participants": ["丹童浩一", "春日野穹"],
            "tags": ["日常", "穹", "清晨", "羁绊"],
        },
        created_at=now_iso,
        updated_at=now_iso,
    )
    await graph_manager.add_node(NOVEL_ID, morning_node)
    print(f"✓ 图谱事件节点已创建：清晨日常 ({morning_node.node_id[:8]})")

    # 最终统计
    msg_count = (await db._fetchone("SELECT COUNT(*) as c FROM messages WHERE novel_id=?", (NOVEL_ID,)) or {}).get('c', 0)
    hook_count_now = (await db._fetchone("SELECT COUNT(*) as c FROM narrative_hooks WHERE novel_id=?", (NOVEL_ID,)) or {}).get('c', 0)
    stats = graph_manager.get_stats(NOVEL_ID)

    print(f"\n[完成] 开局生成结果:")
    print(f"  消息: {msg_count} 条")
    print(f"  伏笔: {hook_count_now} 条")
    print(f"  图谱: 节点={stats.get('node_count','?')} 边={stats.get('edge_count','?')}")
    print(f"\n  正文字数: {len(OPENING_TEXT)} 字")
    print(f"\n✅ 开局已写入，可以在前端查看并继续互动")

if __name__ == '__main__':
    asyncio.run(main())
