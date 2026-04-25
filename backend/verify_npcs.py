import urllib.request, json, sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
url = 'http://localhost:8000/api/narrator/d7830720-bb9a-41d3-9009-f38133d564c1/npcs'
r = urllib.request.urlopen(url)
data = json.loads(r.read())
print(f'总 NPC 数: {data["count"]}')
print()
for npc in data['npcs']:
    print(f'【{npc["name"]}】')
    print(f'  情感类型: {npc["emotion_type"]}  好感度: {npc["initial_affinity"]}')
    print(f'  标签: {" / ".join(npc.get("emotion_tags",[]))}')
    print(f'  关系: {npc["relation_label"][:50]}')
    print(f'  背景: {npc["background"][:60]}')
    print()
